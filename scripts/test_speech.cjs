/* Run with: node --test scripts/test_speech.cjs (no dependencies). */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const speech = require('../static/assistant_app/speech.js');
const english = {name:'Local English', lang:'en-US', localService:true, default:true};
const hindi = {name:'Local Hindi', lang:'hi-IN', localService:true};
const marathi = {name:'Local Marathi', lang:'mr-IN', localService:true};

function fixture(voices = [english, hindi, marathi]) {
  const utterances = [], notices = [], states = [], listeners = {};
  const synth = {getVoices:() => voices, cancelCount:0, cancel() { this.cancelCount++; },
    speak(u) { utterances.push(u); }, addEventListener(name, cb) { listeners[name] = cb; },
    removeEventListener(name) { delete listeners[name]; }};
  const controller = speech.create({synth, Utterance:class {constructor(text) {this.text = text;}},
    onChange:s => states.push(s), onNotice:s => notices.push(s)});
  return {controller, synth, utterances, notices, states, listeners};
}

test('speaks only cleaned answer text, retaining factual numbers', () => {
  assert.equal(speech.plainText('## Budget\n**INR 750,000** [Source 2]\n- See [details](https://example.com).'), 'Budget INR 750,000 See details.');
  assert.equal(speech.plainText('```python\nprint(42)\n```'), 'print(42)');
});
test('detects English, Roman Hinglish, Hindi and Marathi from response text', () => {
  assert.equal(speech.languageFor('The budget is 750000.'), 'en-US');
  assert.equal(speech.languageFor('Budget 750000 hai.'), 'en-IN');
  assert.equal(speech.languageFor('परियोजना का बजट है।'), 'hi-IN');
  assert.equal(speech.languageFor('प्रकल्पाचे बजेट आहे.'), 'mr-IN');
  assert.equal(speech.languageFor('निधी ७५००००', 'Marathi'), 'mr-IN');
});
test('prefers the requested local voice and never selects remote voices', () => {
  assert.equal(speech.selectVoice([english, hindi, marathi], 'mr-IN'), marathi);
  assert.equal(speech.selectVoice([{...hindi, localService:false}, english], 'hi-IN'), english);
  assert.equal(speech.selectVoice([{...english, localService:false}], 'en-US'), undefined);
});
test('Listen, start, completion and Stop update the active answer', () => {
  const f = fixture();
  f.controller.play('one', 'Hello.');
  assert.equal(f.states.at(-1).active, 'one');
  f.utterances[0].onstart(); assert.equal(f.states.at(-1).phase, 'speaking');
  f.utterances[0].onend(); assert.equal(f.states.at(-1).active, null);
  f.controller.play('one', 'Hello again.'); f.controller.play('one', 'Hello again.');
  assert.equal(f.states.at(-1).active, null); assert.equal(f.utterances.length, 2);
});
test('switching answers cancels previous playback and ignores stale callbacks', () => {
  const f = fixture();
  f.controller.play('one', 'First answer.'); const first = f.utterances[0];
  f.controller.play('two', 'Second answer.');
  const cancellations = f.synth.cancelCount;
  first.onend(); first.onerror({error:'canceled'}); first.onstart();
  assert.equal(f.states.at(-1).active, 'two');
  assert.equal(f.synth.cancelCount, cancellations);
  f.controller.stop(); assert.equal(f.states.at(-1).active, null);
});
test('long answers are queued one chunk at a time and stop cancels continuation', () => {
  const f = fixture(); const text = 'This is a sentence. '.repeat(50).trim();
  f.controller.play('one', text);
  assert.equal(f.utterances.length, 1); assert.ok(f.utterances[0].text.length <= 200);
  f.utterances[0].onend(); assert.equal(f.utterances.length, 2);
  f.controller.stop(); f.utterances[1].onend(); assert.equal(f.utterances.length, 2);
  assert.equal(speech.chunks(text).join(' '), text);
});
test('missing API and remote-only voices are disabled with an explanation', () => {
  const notices = [];
  const unsupported = speech.create({onNotice:n => notices.push(n)});
  assert.equal(unsupported.availability().available, false);
  unsupported.play('one', 'Private text'); assert.match(notices[0], /does not support/);
  const f = fixture([{...english, localService:false}]);
  f.controller.play('one', 'Private text');
  assert.equal(f.utterances.length, 0); assert.match(f.notices[0], /Online voices are not used/);
});
test('voiceschanged enables local audio after asynchronous voice loading', () => {
  const voices = [], f = fixture(voices);
  assert.equal(f.controller.availability().available, false);
  voices.push(english); f.listeners.voiceschanged();
  assert.equal(f.states.at(-1).available, true);
  f.controller.destroy(); assert.equal(f.listeners.voiceschanged, undefined);
});
test('missing language and Roman Hinglish pronunciation limitations are explained', () => {
  const f = fixture([english]);
  f.controller.play('one', 'प्रकल्पाचे बजेट आहे.');
  assert.equal(f.utterances[0].voice, english); assert.match(f.notices[0], /No local Marathi/);
  f.controller.play('two', 'Budget itna hai.'); assert.match(f.notices.at(-1), /Roman Hinglish/);
  f.controller.stop();
});
test('speech errors and synchronous browser exceptions reset playback safely', () => {
  const f = fixture(); f.controller.play('one', 'Hello');
  f.utterances[0].onerror({error:'not-allowed'});
  assert.equal(f.states.at(-1).active, null); assert.match(f.notices[0], /blocked/);
  f.synth.speak = () => {throw Error('Browser failure');};
  f.controller.play('two', 'Hello'); assert.equal(f.states.at(-1).active, null);
  assert.match(f.notices.at(-1), /could not start/);
});
