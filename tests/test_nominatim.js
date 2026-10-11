const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.join(__dirname, '..', 'docs', 'setup', 'js', 'nominatim.js'), 'utf8'
);

function setup({failFirst = false, firstRequestDuration = 0} = {}) {
    let now = 0;
    const starts = [];
    const delays = [];
    const context = {
        URLSearchParams,
        Date: {now: () => now},
        console: {error: () => undefined},
        setTimeout(callback, delay) {
            delays.push(delay);
            queueMicrotask(() => {
                now += delay;
                callback();
            });
        },
        async fetch(url) {
            starts.push(now);
            if (starts.length === 1) {
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
    return {context, starts, delays};
}

test('concurrent forward and reverse lookups start at least one second apart', async () => {
    const {context, starts} = setup();
    const [city, coordinates] = await Promise.all([
        context.geocodeLocation('Brussels', 'BE'),
        context.reverseGeocodeLocation(50.8505, 4.3488),
        context.geocodeLocation('Budapest', 'HU')
    ]);

    assert.equal(city.lat, 50.8505);
    assert.equal(coordinates.country_code, 'BE');
    assert.deepEqual(starts, [0, 1000, 2000]);
});

test('cross-verification respects the same request queue', async () => {
    const {context, starts} = setup();
    const result = await context.crossVerifyLocation({
        lat: 50.8505, lon: 4.3488, city: 'Brussels', country: 'BE'
    });

    assert.equal(result.match, true);
    assert.deepEqual(starts, [0, 1000]);
});

test('a failed request releases the queue and preserves request spacing', async () => {
    const {context, starts} = setup({failFirst: true});
    const results = await Promise.allSettled([
        context.geocodeLocation('Brussels', 'BE'),
        context.reverseGeocodeLocation(50.8505, 4.3488)
    ]);

    assert.equal(results[0].status, 'rejected');
    assert.equal(results[1].status, 'fulfilled');
    assert.deepEqual(starts, [0, 1000]);
});

test('a slow response already satisfies the interval without another delay', async () => {
    const {context, starts, delays} = setup({firstRequestDuration: 1500});
    await Promise.all([
        context.geocodeLocation('Brussels', 'BE'),
        context.reverseGeocodeLocation(50.8505, 4.3488)
    ]);

    assert.deepEqual(starts, [0, 1500]);
    assert.deepEqual(delays, []);
});
