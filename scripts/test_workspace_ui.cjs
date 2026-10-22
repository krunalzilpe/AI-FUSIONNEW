/* DOM checks, not a visual browser test. Install jsdom in the ignored test area:
   npm install --prefix .local-backup/ui-test-tools --no-save --package-lock=false --ignore-scripts jsdom@27.0.1
   node --test scripts/test_workspace_ui.cjs */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require('../.local-backup/ui-test-tools/node_modules/jsdom');
const template = fs.readFileSync('templates/assistant_app/dashboard.html', 'utf8');
const scripts = ['speech', 'workspace'].map(name => fs.readFileSync(`static/assistant_app/${name}.js`, 'utf8'));
const docs = [
  {id:1, title:'Original plan.pdf', file_type:'pdf', status:'ready', page_count:3, chunk_count:3, url:'/document/1/source/', uploaded_at:'2026-10-22T00:00:00Z'},
  {id:2, title:'Notes.txt', file_type:'txt', status:'ready', chunk_count:1, url:'/document/2/source/', uploaded_at:'2026-10-22T00:00:00Z'},
];
const turns = [
  {question:'What is the budget?', answer:'The budget is **750000**. [Source 1]', mode:'gemini', query_metadata:{documents:[1], language_hint:'Auto / English'}, sources:[{title:'Original plan.pdf', file_type:'pdf', page:2, chunk_index:1, text:'The budget is 750000.', score:0.8, url:'/document/1/source/#page=2'}]},
  {question:'What is the release code?', answer:'The code is AURORA-42. [Source 1]', mode:'gemini', query_metadata:{documents:[2]}, sources:[{title:'Notes.txt', file_type:'txt', page:null, chunk_index:0, text:'The release code is AURORA-42.', score:0.9, url:'/document/2/source/'}]},
];
const flush = async () => { for (let i=0; i<4; i++) await new Promise(resolve => setImmediate(resolve)); };

function setup({saved, speech = true, voices} = {}) {
  const initial = {documents:docs, conversations:[{id:7,title:'Saved conversation'}], display_name:'Guest', workspace_key:'guest:test', gemini_configured:false};
  const html = template.replace('{% csrf_token %}', '<input name="csrfmiddlewaretoken" value="test">')
    .replace('{{ initial|json_script:"workspace-initial" }}', `<script id="workspace-initial" type="application/json">${JSON.stringify(initial)}</script>`)
    .replace(/{%[\s\S]*?%}/g, '');
  const dom = new JSDOM(html, {url:'http://localhost:8001/', runScripts:'outside-only'});
  const w = dom.window, d = w.document, requests = [], copied = [], spoken = [], mediaEvents = [];
  w.matchMedia = () => ({matches:true, addEventListener:(_, fn) => mediaEvents.push(fn)});
  w.requestAnimationFrame = fn => fn(); w.HTMLElement.prototype.scrollIntoView = function() {};
  w.confirm = () => true; w.navigator.clipboard = {writeText: async text => copied.push(text)};
  if (saved) w.localStorage.setItem('documind-theme', saved);
  if (speech) {
    w.speechSynthesis = {getVoices:() => voices || [{name:'Local English', lang:'en-US', localService:true}],
      cancelCount:0, cancel() {this.cancelCount++;}, speak:u => spoken.push(u), addEventListener() {}, removeEventListener() {}};
    w.SpeechSynthesisUtterance = class {constructor(text) {this.text = text;}};
  }
  w.fetch = async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : undefined;
    requests.push({url, body}); let result;
    if (url === '/conversation/7/') result = {conversation:{id:7,documents:[1,2]}, turns};
    else if (url === '/conversations/') result = {conversations:initial.conversations};
    else if (url === '/ask/') result = {...turns[0], conversation_id:7};
    else if (url === '/documents/') result = {documents:docs};
    else throw Error(`Unexpected request ${url}`);
    return {ok:true,json:async () => result};
  };
  const prepaint = d.querySelector('head script').textContent;
  w.eval(prepaint); const initialTheme = d.documentElement.dataset.theme;
  scripts.forEach(script => w.eval(script));
  return {w,d,requests,copied,spoken,mediaEvents,initialTheme,dom,
    async history() {d.querySelector('[data-conversation]').click(); await flush();},
    close() {w.dispatchEvent(new w.Event('pagehide')); w.close();}};
}

test('first visit is light despite dark OS; selectors sync and persist; prepaint honors saved dark', () => {
  const f = setup();
  assert.equal(f.initialTheme, 'light'); assert.equal(f.d.documentElement.dataset.theme, 'light');
  const selector = f.d.getElementById('sidebar-theme'); selector.value = 'dark';
  selector.dispatchEvent(new f.w.Event('change'));
  assert.equal(f.d.documentElement.dataset.theme, 'dark');
  assert.equal(f.d.getElementById('theme-select').value, 'dark');
  assert.equal(f.w.localStorage.getItem('documind-theme'), 'dark'); f.close();
  const restored = setup({saved:'dark'}); assert.equal(restored.initialTheme, 'dark'); restored.close();
  const invalid = setup({saved:'invalid'}); assert.equal(invalid.initialTheme,'light'); invalid.close();
});
test('history sources stay attached to their own answer and TXT has no page label', async () => {
  const f = setup(); await f.history();
  const answers = f.d.querySelectorAll('.turn'); assert.equal(answers.length, 2);
  answers[0].querySelector('[data-view-sources]').click();
  assert.equal(answers[0].querySelector('.source-card').open, true);
  assert.equal(answers[1].querySelector('.source-card').open, false);
  answers[0].querySelector('.inline-citation').click();
  assert.match(f.d.getElementById('source-preview').textContent, /Original plan.pdf/);
  assert.match(f.d.querySelector('.preview-meta').textContent, /Page 2/);
  answers[1].querySelector('.inline-citation').click();
  assert.match(f.d.getElementById('source-preview').textContent, /AURORA-42/);
  assert.doesNotMatch(answers[1].querySelector('.source-card').textContent, /Page \d/);
  answers[0].querySelector('[data-view-sources]').click();
  assert.equal(answers[0].querySelector('.source-card').open, false); f.close();
});
test('Copy Answer copies only the selected answer and shows success feedback', async () => {
  const f = setup(); await f.history();
  f.d.querySelectorAll('[data-copy]')[1].click(); await flush();
  assert.deepEqual(f.copied, [turns[1].answer]);
  assert.match(f.d.getElementById('notification').textContent, /Answer copied/); f.close();
});
test('Listen, switching, Stop and New Chat update controls without making API requests', async () => {
  const f = setup(); await f.history(); const calls = f.requests.length;
  const buttons = f.d.querySelectorAll('[data-listen]');
  buttons[0].click(); assert.match(buttons[0].textContent, /Stop Audio/);
  f.spoken[0].onstart(); assert.match(f.d.querySelector('.audio-status').textContent, /Reading answer aloud/);
  assert.doesNotMatch(f.spoken[0].text, /Source|Original plan|Copy|\*\*/);
  buttons[1].click(); assert.match(buttons[0].textContent, /Listen/);
  assert.match(buttons[1].textContent, /Stop Audio/);
  f.spoken[0].onend(); assert.equal(buttons[1].getAttribute('aria-pressed'), 'true');
  buttons[1].click(); assert.equal(buttons[1].getAttribute('aria-pressed'), 'false');
  buttons[0].click(); const cancelled = f.w.speechSynthesis.cancelCount;
  f.d.getElementById('new-chat-btn').click(); assert.ok(f.w.speechSynthesis.cancelCount > cancelled);
  assert.equal(f.requests.length, calls); f.close();
});
test('unsupported speech and remote-only voices disable Listen with visible explanations', async () => {
  for (const options of [{speech:false},{voices:[{lang:'en-US',localService:false}]}]) {
    const f = setup(options); await f.history();
    assert.equal(f.d.querySelector('[data-listen]').disabled, true);
    assert.equal(f.d.querySelector('.audio-status').hidden, false);
    assert.match(f.d.querySelector('.audio-status').textContent, /does not support|No local voice/); f.close();
  }
});
test('Regenerate uses original documents, prevents duplicate submits and preserves old turns', async () => {
  const f = setup(); await f.history();
  const firstDoc = f.d.querySelector('[data-select-doc="1"]'); firstDoc.checked = false;
  firstDoc.dispatchEvent(new f.w.Event('change', {bubbles:true}));
  const regenerate = f.d.querySelector('[data-regenerate]'); regenerate.click(); regenerate.click();
  assert.equal(f.d.getElementById('send-btn').disabled, true);
  await flush();
  const requests = f.requests.filter(r => r.url === '/ask/'); assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].body.documents, [1]); assert.equal(requests[0].body.conversation_id, 7);
  assert.equal(f.d.querySelectorAll('.turn').length, 3);
  assert.match(f.d.querySelectorAll('.turn')[1].textContent, /AURORA-42/);
  assert.equal(f.d.getElementById('send-btn').disabled, false); f.close();
});
test('clipboard denial and chat failure show honest errors and restore the composer', async () => {
  const f = setup(); await f.history();
  f.w.navigator.clipboard.writeText = async () => {throw Error('Denied');};
  f.d.querySelector('[data-copy]').click(); await flush();
  assert.match(f.d.getElementById('notification').textContent, /Clipboard unavailable/);
  f.w.fetch = async () => ({ok:false, json:async () => ({success:false, error:'Provider temporarily unavailable', mode:'provider_error'})});
  f.d.getElementById('question-input').value = 'What is the budget?';
  f.d.getElementById('question-form').dispatchEvent(new f.w.Event('submit', {cancelable:true})); await flush();
  const errorTurn = [...f.d.querySelectorAll('.turn')].at(-1);
  assert.match(errorTurn.textContent, /Provider temporarily unavailable/);
  assert.equal(errorTurn.querySelector('[data-view-sources]').disabled, true);
  assert.equal(errorTurn.querySelector('[data-regenerate]'), null);
  assert.equal(f.d.getElementById('send-btn').disabled, false); f.close();
});
test('system preference remains opt-in and unavailable original documents disable regeneration', async () => {
  const f = setup({saved:'system'}); assert.equal(f.initialTheme,'dark'); await f.history();
  f.w.fetch = async url => ({ok:true,json:async () => url === '/documents/' ? {documents:[docs[1]]} : {success:true}});
  f.d.querySelector('[data-delete-doc="1"]').click(); await flush();
  assert.equal(f.d.querySelector('[data-regenerate]').disabled, true);
  assert.match(f.d.querySelector('[data-regenerate]').title,/removed/);
  assert.equal(f.d.querySelectorAll('[data-regenerate]')[1].disabled, false); f.close();
});
