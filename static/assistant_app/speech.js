/* Local browser voices only. This module never makes a network request. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DocuMindSpeech = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function plainText(answer) {
    return String(answer || '')
      .replace(/```[^\n]*\n?/g, '\n')
      .replace(/\[\s*Source\s+\d+\s*\]/gi, '')
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .replace(/https?:\/\/\S+/g, '')
      .replace(/^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+\.\s+)/gm, '')
      .replace(/[*_`~|]/g, '')
      .replace(/\s+/g, ' ').trim();
  }

  function languageFor(text, hint = '') {
    if (/[\u0900-\u097f]/.test(text)) {
      return /marathi/i.test(hint) || /मराठी|आहे|आहेत|मध्ये|आणि|साठी|याचा|करण्यात/.test(text) ? 'mr-IN' : 'hi-IN';
    }
    return /hinglish/i.test(hint) || /\b(hai|hain|bhai|aap|iska|isme|samjha|batao|mein|likha|kya)\b/i.test(text) ? 'en-IN' : 'en-US';
  }

  function selectVoice(voices, language) {
    const local = voices.filter(v => v.localService === true);
    const normalize = lang => String(lang).replace(/_/g, '-').toLowerCase();
    return local.find(v => normalize(v.lang) === normalize(language)) ||
      local.find(v => normalize(v.lang).split('-')[0] === language.split('-')[0]) ||
      local.find(v => v.default) || local.find(v => /^en\b/i.test(v.lang)) || local[0];
  }

  // Short utterances avoid browser limits on long answers; only one is queued.
  function chunks(text) {
    const result = [];
    let rest = text;
    while (rest.length > 200) {
      let end = rest.lastIndexOf(' ', 200);
      if (end < 1) end = 200;
      result.push(rest.slice(0, end)); rest = rest.slice(end).trim();
    }
    if (rest) result.push(rest);
    return result;
  }

  function create({synth, Utterance, onChange = () => {}, onNotice = () => {}}) {
    const supported = Boolean(synth && Utterance);
    let active = null, currentUtterance = null, generation = 0, timer;
    function availability() {
      if (!supported) return {available: false, reason: 'Audio is unavailable: this browser does not support speech synthesis.'};
      if (!synth.getVoices().some(v => v.localService === true)) return {available: false, reason: 'No local voice is available yet. Enable a device voice and reload. Online voices are not used for private answers.'};
      return {available: true, reason: 'Uses a local device voice. Available languages depend on your browser and installed voices.'};
    }
    function emit(phase = 'idle') { onChange({active, phase, ...availability()}); }
    function stop() {
      generation += 1; clearTimeout(timer); active = null; currentUtterance = null;
      if (supported) synth.cancel();
      emit();
    }
    function play(key, answer, hint) {
      if (active === key) { stop(); return; }
      stop();
      const status = availability();
      if (!status.available) { onNotice(status.reason); return; }
      const text = plainText(answer);
      if (!text) { onNotice('There is no answer text to read.'); return; }
      const language = languageFor(text, hint), voice = selectVoice(synth.getVoices(), language);
      if (voice.lang.toLowerCase().split(/[-_]/)[0] !== language.split('-')[0]) {
        onNotice(`No local ${language.startsWith('mr') ? 'Marathi' : language.startsWith('hi') ? 'Hindi' : 'English'} voice is installed. Using ${voice.name} (${voice.lang}); pronunciation may be limited.`);
      } else if (language === 'en-IN') {
        onNotice(`Reading Roman Hinglish with ${voice.name}. Mixed-language pronunciation varies by device.`);
      }
      active = key; const token = generation, parts = chunks(text); let index = 0;
      function next() {
        if (token !== generation) return;
        if (index === parts.length) { active = null; currentUtterance = null; emit(); return; }
        const utterance = new Utterance(parts[index++]); currentUtterance = utterance;
        utterance.voice = voice; utterance.lang = voice.lang; utterance.rate = 1;
        utterance.onstart = () => { if (token === generation && currentUtterance === utterance) emit('speaking'); };
        utterance.onend = () => {
          if (token !== generation || currentUtterance !== utterance) return;
          clearTimeout(timer); next();
        };
        utterance.onerror = event => {
          if (token !== generation || currentUtterance !== utterance) return;
          stop();
          onNotice(event.error === 'not-allowed' ? 'Audio was blocked by the browser. Click Listen to try again.' : 'Audio could not play. Check your device voice settings and try again.');
        };
        emit('starting');
        timer = setTimeout(() => { if (token === generation) { stop(); onNotice('Audio stopped responding. Click Listen to try again.'); } }, 45000);
        try { synth.speak(utterance); } catch (_) { stop(); onNotice('Audio could not start in this browser.'); }
      }
      next();
    }
    const refresh = () => emit(active ? 'speaking' : 'idle');
    if (supported) synth.addEventListener?.('voiceschanged', refresh);
    return {play, stop, availability, destroy() { stop(); synth?.removeEventListener?.('voiceschanged', refresh); }};
  }
  return {create, plainText, languageFor, selectVoice, chunks};
});
