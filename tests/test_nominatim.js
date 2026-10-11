const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.join(__dirname, '..', 'docs', 'setup', 'js', 'nominatim.js'), 'utf8'
);

function setup({failFirst = false, firstRequestDuration = 0, stallFirst = false,
    ignoreAbort = false} = {}) {
    let now = 0;
    let nextTimer = 1;
    let aborts = 0;
    const starts = [];
    const timers = new Map();
    const context = {
        URLSearchParams,
        AbortController,
        Date: {now: () => now},
        console: {error: () => undefined},
        setTimeout(callback, delay) {
            const id = nextTimer++;
            timers.set(id, {callback, at: now + delay});
            return id;
        },
        clearTimeout(id) {
            timers.delete(id);
        },
        async fetch(url, options) {
            starts.push(now);
            if (starts.length === 1) {
                if (stallFirst) {
                    return new Promise((resolve, reject) => {
                        options.signal.addEventListener('abort', () => {
                            aborts++;
                            if (!ignoreAbort) reject(new Error('request aborted'));
                        }, {once: true});
                    });
                }
                now += firstRequestDuration;
                if (failFirst) throw new Error('network unavailable');
            }
            return {
                ok: true,
                async json() {
                    return url.includes('/reverse?')
                        ? {address: {city: 'Brussels', country_code: 'be'}, display_name: 'Brussels'}
                        : [{lat: '50.8505', lon: '4.3488', display_name: 'Brussels'}];
                }
            };
        }
    };
    context.window = context;
    vm.runInNewContext(source, context);
    const flush = () => new Promise(resolve => setImmediate(resolve));
    async function advance(ms) {
        const target = now + ms;
        await flush();
        while (timers.size > 0) {
            const [id, timer] = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
            if (timer.at > target) break;
            now = timer.at;
            timers.delete(id);
            timer.callback();
            await flush();
        }
        now = target;
        await flush();
    }
    async function settle(promise) {
        let complete = false;
        promise.then(() => { complete = true; }, () => { complete = true; });
        await flush();
        for (let attempts = 0; !complete && attempts < 20; attempts++) {
            assert.ok(timers.size > 0, 'pending request has no deadline or rate-limit timer');
            await advance(Math.min(...[...timers.values()].map(timer => timer.at)) - now);
        }
        assert.ok(complete, 'request did not settle after running scheduled timers');
        return promise;
    }
    return {context, starts, timers, advance, settle, getAborts: () => aborts};
}

test('concurrent forward and reverse lookups start at least one second apart', async () => {
    const {context, starts, settle} = setup();
    const [city, coordinates] = await settle(Promise.all([
        context.geocodeLocation('Brussels', 'BE'),
        context.reverseGeocodeLocation(50.8505, 4.3488),
        context.geocodeLocation('Budapest', 'HU')
    ]));

    assert.equal(city.lat, 50.8505);
    assert.equal(coordinates.country_code, 'BE');
    assert.deepEqual(starts, [0, 1000, 2000]);
});

test('cross-verification respects the same request queue', async () => {
    const {context, starts, settle} = setup();
    const result = await settle(context.crossVerifyLocation({
        lat: 50.8505, lon: 4.3488, city: 'Brussels', country: 'BE'
    }));

    assert.equal(result.match, true);
    assert.deepEqual(starts, [0, 1000]);
});

test('a failed request releases the queue and preserves request spacing', async () => {
    const {context, starts, settle} = setup({failFirst: true});
    const results = await settle(Promise.allSettled([
        context.geocodeLocation('Brussels', 'BE'),
        context.reverseGeocodeLocation(50.8505, 4.3488)
    ]));

    assert.equal(results[0].status, 'rejected');
    assert.equal(results[1].status, 'fulfilled');
    assert.deepEqual(starts, [0, 1000]);
});

test('a slow response already satisfies the interval without another delay', async () => {
    const {context, starts, timers, settle} = setup({firstRequestDuration: 1500});
    await settle(Promise.all([
        context.geocodeLocation('Brussels', 'BE'),
        context.reverseGeocodeLocation(50.8505, 4.3488)
    ]));

    assert.deepEqual(starts, [0, 1500]);
    assert.equal(timers.size, 0);
});

for (const ignoreAbort of [false, true]) {
    test(`a stalled request releases the queue when its deadline expires (ignore abort: ${ignoreAbort})`, async () => {
        const {context, starts, timers, advance, getAborts} = setup({stallFirst: true, ignoreAbort});
        const lookups = Promise.allSettled([
            context.geocodeLocation('Brussels', 'BE'),
            context.reverseGeocodeLocation(50.8505, 4.3488),
            context.geocodeLocation('Budapest', 'HU')
        ]);

        await advance(9999);
        assert.deepEqual(starts, [0]);
        assert.equal(getAborts(), 0);
        await advance(1);
        assert.deepEqual(starts, [0, 10000]);
        assert.equal(getAborts(), 1);
        await advance(1000);
        const results = await lookups;

        assert.equal(results[0].status, 'rejected');
        assert.match(results[0].reason.message, /timed out/);
        assert.equal(results[1].status, 'fulfilled');
        assert.equal(results[1].value.country_code, 'BE');
        assert.equal(results[2].status, 'fulfilled');
        assert.deepEqual(starts, [0, 10000, 11000]);
        assert.equal(timers.size, 0);
    });
}
