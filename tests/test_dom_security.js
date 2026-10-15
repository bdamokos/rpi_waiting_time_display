const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const {before, after, test} = require('node:test');
const {chromium} = require('playwright');

const root = path.resolve(process.env.DOM_SECURITY_ROOT || path.join(__dirname, '..'));
const htmlPayload = '<img src="missing" onerror="window.__xss = true">';
const attributePayload = '" onmouseover="window.__xss = true" data-test="';
const driverPayload = "driver');window.__xss = true;//";
let browser;
let server;
let origin;

function database(value = 'Waveshare') {
    return {
        categories: {manufacturers: [value], sizes: ['2.13'], colors: ['Black', 'White']},
        displays: [{id: 'test', name: 'Paper & Ink', manufacturer: value, size: '2.13',
            driver: 'epd2in13_V4', preset: 'standard', resolution: {width: 250, height: 122},
            colors: ['Black', 'White'], features: {partial_refresh: true},
            notes: 'A < B & C', url: 'https://example.test/display', images: ['/image.png']}],
        presets: {standard: {settings: {refresh_interval: 90, refresh_minimal_time: 30,
            refresh_weather_interval: 600, refresh_full_interval: 3600,
            flight_display_fast_mode_interval: 5, iss_check_interval: 30}}}
    };
}

before(async () => {
    server = http.createServer((request, response) => {
        const filename = path.resolve(root, '.' + new URL(request.url, 'http://localhost').pathname);
        if (!filename.startsWith(root + path.sep) || !fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
            response.writeHead(404).end();
            return;
        }
        response.setHeader('Content-Type', {'.js': 'text/javascript', '.css': 'text/css',
            '.json': 'application/json'}[path.extname(filename)] || 'text/html');
        response.end(fs.readFileSync(filename));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    origin = `http://127.0.0.1:${server.address().port}`;
    browser = await chromium.launch({headless: true,
        channel: process.env.PLAYWRIGHT_BROWSER_CHANNEL || undefined});
});

after(async () => {
    if (browser) await browser.close();
    if (server) await new Promise(resolve => server.close(resolve));
});

async function pageFor(t, {editor = false, data = database()} = {}) {
    const page = await browser.newPage();
    t.after(() => page.close());
    await page.route('**/*', route => {
        if (route.request().url().endsWith('/data/displays.json')) {
            return route.fulfill({json: data});
        }
        return route.request().url().startsWith(origin + '/') ? route.continue() : route.abort();
    });
    if (editor) {
        await page.goto(origin + '/docs/dev/display_db_editor.html');
        await page.waitForFunction(() => document.querySelector('#jsonEditor').value !== '');
    } else {
        await page.goto(origin + '/docs/data/displays.json');
        await page.setContent('<div id="step-content"></div><div id="display-setup"></div>' +
            '<button id="display-setup-button"></button><div id="display-selection-container"></div>' +
            '<div id="matching-displays"></div><select id="size-select"></select>' +
            '<div id="provider-config"></div><div id="transit-setup"></div>' +
            '<button id="transit-setup-button"></button><input id="latitude" value="50.8">' +
            '<input id="longitude" value="4.3"><input id="city"><input id="country" value="BE">' +
            '<div id="cross-verification"></div><div id="coords-verification"></div>' +
            '<div id="city-verification"></div>');
        const helper = path.join(root, 'docs/setup/js/safe_dom.js');
        if (fs.existsSync(helper)) await page.addScriptTag({path: helper});
    }
    return page;
}

async function assertInert(page) {
    await page.evaluate(() => {
        document.querySelectorAll('*').forEach(element => {
            element.dispatchEvent(new MouseEvent('mouseover'));
            element.dispatchEvent(new Event('error'));
        });
    });
    assert.equal(await page.evaluate(() => Boolean(window.__xss)), false);
    assert.equal(await page.locator('[onerror], [onmouseover]').count(), 0);
}

for (const [field, alert] of [['manufacturers', 16], ['sizes', 17], ['colors', 18]]) {
    test(`CodeQL #${alert}: editable ${field} remain literal text and values`, async t => {
        const page = await pageFor(t, {editor: true});
        const values = database();
        values.categories[field] = [attributePayload, htmlPayload];
        await page.evaluate(data => { populateFormSelections(data); }, values);
        await assertInert(page);
        const selector = field === 'colors' ? '#colors input' : `#${field === 'sizes' ? 'size' : 'manufacturer'} option`;
        assert.deepEqual(await page.locator(selector).evaluateAll(nodes => nodes.map(n => n.value)),
            [attributePayload, htmlPayload]);
    });
}

test('CodeQL #19: image preview does not parse input as attributes', async t => {
    const page = await pageFor(t, {editor: true});
    await page.locator('#images').fill('https://example.test/" onerror="window.__xss=true');
    await assertInert(page);
    assert.equal(await page.locator('#imagePreview img').count(), 1);
});

test('CodeQL #20: database preview preserves text and rejects executable URLs', async t => {
    const page = await pageFor(t, {editor: true});
    const data = database(htmlPayload);
    Object.assign(data.displays[0], {name: htmlPayload, notes: htmlPayload,
        driver: attributePayload, url: 'JaVaScRiPt:window.__xss=true',
        images: ['data:text/html,<script>window.__xss=true</script>', attributePayload]});
    await page.evaluate(value => updatePreview(value), data);
    await assertInert(page);
    assert.equal(await page.locator('#preview h4').textContent(), htmlPayload);
    assert.equal(await page.locator('#preview a').evaluateAll(nodes => nodes.some(n =>
        /^(javascript|data):/i.test(n.href))), false);
});

test('CodeQL #21: display settings preserve device values without HTML or inline-JS execution', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/display_setup.js')});
    await page.evaluate(({data, value}) => {
        window.displayDatabase = data;
        window.setupDevice = {send: async () => ({status: 'success', value})};
    }, {data: database(), value: htmlPayload});
    await page.evaluate(driver => showDisplaySettings(driver), driverPayload);
    await assertInert(page);
    assert.ok((await page.locator('.preset-settings').textContent()).includes(htmlPayload));
    await page.evaluate(() => { window.showAdvancedSettings = driver => { window.chosenDriver = driver; }; });
    await page.locator('.advanced-settings-button').click();
    assert.equal(await page.evaluate(() => window.chosenDriver), driverPayload);
    await assertInert(page);
});

test('CodeQL #22: location mismatch treats user and geocoder names as text', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/location_setup.js')});
    await page.locator('#city').fill(htmlPayload);
    await page.evaluate(payload => {
        window.crossVerifyLocation = async () => ({match: false, details: {distance: 1,
            cityMatch: false, countryMatch: true,
            fromCoords: {display_name: payload, city: payload, country_code: 'BE'},
            fromCity: {lat: '50.8', lon: '4.3'}}});
    }, htmlPayload);
    await page.evaluate(() => crossVerifyInputs());
    await assertInert(page);
    assert.ok((await page.locator('#cross-verification').textContent()).includes(htmlPayload));
});

test('CodeQL #23: transit form rejects unsupported provider values', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/transit_setup.js')});
    await page.evaluate(provider => {
        window.showError = value => { window.providerError = value; };
        showProviderConfig(provider);
    }, driverPayload);
    await assertInert(page);
    assert.equal(await page.locator('#provider-config .button').count(), 0);
    assert.equal(await page.evaluate(() => window.providerError), 'Unsupported transit provider');
});

test('ordinary database editor and relative/HTTPS image links remain usable', async t => {
    const page = await pageFor(t, {editor: true});
    assert.equal(await page.locator('#preview h4').textContent(), 'Paper & Ink');
    assert.ok((await page.locator('#preview').textContent()).includes('A < B & C'));
    assert.equal(await page.locator('#preview a').first().getAttribute('href'), 'https://example.test/display');
    await page.locator('#images').fill('/images/panel.png,https://example.test/panel.png');
    assert.equal(await page.locator('#imagePreview img').count(), 2);
    assert.ok((await page.locator('#imagePreview img').first().getAttribute('src')).endsWith('/images/panel.png'));
});

test('all transit forms retain their ordinary save action and fields', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/transit_setup.js')});
    for (const provider of ['stib', 'delijn', 'bkk', 'sncb', 'other']) {
        await page.evaluate(value => {
            showProviderConfig(value);
            window.saveTransitConfig = selected => { window.chosenProvider = selected; };
        }, provider);
        assert.equal(await page.locator('#stop-id').count(), 1);
        assert.equal(await page.locator('#server-url').inputValue(), 'http://localhost:8000');
        await page.locator('#provider-config .button').click();
        assert.equal(await page.evaluate(() => window.chosenProvider), provider);
    }
});

test('lookup buttons and errors keep geocoder markup inert', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/location_setup.js')});
    await page.evaluate(payload => {
        window.reverseGeocodeLocation = async () => ({display_name: payload});
    }, htmlPayload);
    await page.evaluate(() => verifyCoordinates());
    await assertInert(page);
    assert.ok((await page.locator('#coords-verification').textContent()).includes(htmlPayload));
    await page.evaluate(payload => {
        window.reverseGeocodeLocation = async () => { throw new Error(payload); };
    }, htmlPayload);
    await page.evaluate(() => verifyCoordinates());
    await assertInert(page);
    assert.ok((await page.locator('#coords-verification').textContent()).includes(htmlPayload));
});

test('display list, guided selection and settings callbacks preserve literal driver data', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/display_setup.js')});
    const data = database();
    Object.assign(data.displays[0], {driver: driverPayload, name: htmlPayload,
        url: 'javascript:window.__xss=true', images: [attributePayload], notes: htmlPayload});
    data.categories.colors = [attributePayload];
    await page.evaluate(value => {
        window.displayDatabase = value;
        window.selectDisplay = selected => { window.chosenDriver = selected; };
        showDisplayList();
    }, data);
    await assertInert(page);
    await page.locator('.display-card').click();
    assert.equal(await page.evaluate(() => window.chosenDriver), driverPayload);
    await page.evaluate(() => showDisplaySelection());
    await assertInert(page);
    await page.locator('.set-driver-button').click();
    assert.equal(await page.evaluate(() => window.chosenDriver), driverPayload);
    await page.evaluate(({value}) => {
        showAdvancedSettings(value, {refresh_interval: '" onfocus="window.__xss=true'});
        window.showDisplaySettings = selected => { window.chosenDriver = selected; };
    }, {value: driverPayload});
    await assertInert(page);
    assert.equal(await page.locator('[onfocus]').count(), 0);
    await page.locator('[data-display-action="settings"]').click();
    assert.equal(await page.evaluate(() => window.chosenDriver), driverPayload);
});

test('URL actions reject executable/invalid schemes and preserve relative links', async t => {
    const page = await pageFor(t, {editor: true});
    await page.evaluate(() => { window.open = url => { window.openedUrl = url; }; });
    for (const value of ['javascript:window.__xss=true', ' \nJaVa\tScRiPt:window.__xss=true',
        'data:text/html,<svg onload="window.__xss=true">', 'https://[invalid']) {
        await page.locator('#url').fill(value);
        await page.evaluate(() => testDisplayUrl());
        assert.equal(await page.evaluate(() => window.openedUrl), undefined);
    }
    for (const value of ['../images/panel.png', '//example.test/panel.png', 'https://example.test/panel?a=1&b=2']) {
        await page.locator('#url').fill(value);
        await page.evaluate(() => testDisplayUrl());
        assert.equal(await page.evaluate(() => window.openedUrl), new URL(value,
            origin + '/docs/dev/display_db_editor.html').href);
    }
});

test('saved transit data and custom GTFS IDs remain literal and usable', async t => {
    const page = await pageFor(t);
    await page.addScriptTag({path: path.join(root, 'docs/setup/js/transit_setup.js')});
    await page.evaluate(payload => {
        window.setupDevice = {send: async () => ({status: 'success', variables: {
            Provider: {value: payload}, Stops: {value: '2100'}, Lines: {value: payload},
            Stop_name_override: {value: payload}, BUS_SCHEDULE_URL: {value: payload}
        }})};
    }, htmlPayload);
    await page.evaluate(() => initTransitSetup());
    await assertInert(page);
    assert.equal(await page.locator('#gtfs-provider').inputValue(), htmlPayload);
    assert.equal(await page.locator('#stop-id').inputValue(), '2100');
});

test('normal editor validation, add and save preserve special characters as data', async t => {
    const page = await pageFor(t, {editor: true});
    await page.locator('#name').fill('New <Panel> & Ink');
    await page.locator('#id').fill('new-panel');
    await page.locator('#driver').fill('epd2in13_V4');
    await page.locator('#width').fill('250');
    await page.locator('#height').fill('122');
    await page.evaluate(() => addNewDisplay({preventDefault() {}}));
    assert.equal(await page.locator('#preview h4').last().textContent(), 'New <Panel> & Ink');
    await page.evaluate(() => validateJson());
    assert.ok((await page.locator('#validationMessage').textContent()).includes('Valid JSON'));
    let saved;
    await page.route('**/dev/command', async route => {
        saved = route.request().postDataJSON();
        await route.fulfill({json: {status: 'success', message: htmlPayload}});
    });
    await page.evaluate(() => saveJson());
    await assertInert(page);
    assert.equal(saved.content.displays[1].name, 'New <Panel> & Ink');
    assert.ok((await page.locator('#validationMessage').textContent()).includes(htmlPayload));
});

test('setup entry page loads safe rendering helpers before display setup', async t => {
    const page = await pageFor(t);
    await page.goto(origin + '/docs/setup/index.html');
    await page.waitForFunction(() => typeof window.startDisplaySetup === 'function');
    await page.evaluate(() => {
        window.setupDevice = {connected: true, send: async payload => ({status: 'success',
            value: JSON.parse(payload).key === 'display_model' ? 'epd2in13_V4' : '600'})};
        document.querySelector('#connect-prompt').style.display = 'none';
        document.querySelector('#setup-interface').style.display = 'block';
    });
    await page.locator('#display-setup-button').click();
    await page.locator('[data-display-action="settings"]').click();
    await page.locator('.advanced-settings-button').click();
    assert.equal(await page.locator('#refresh-interval').inputValue(), '600');
    await assertInert(page);
});
