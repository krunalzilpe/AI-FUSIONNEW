'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const initial = JSON.parse($('workspace-initial').textContent);
  const readyDocuments = initial.documents.filter(d => d.status === 'ready');
  const state = {documents: initial.documents, conversations: initial.conversations, selected: new Set(readyDocuments.map(d => d.id)), chatMode: readyDocuments.length ? 'documents' : 'general', conversation: null, busy: false, uploading: false};
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const activeStatuses = ['queued', 'extracting', 'embedding', 'indexing'];
  let noticeTimer, polling = false;

  async function api(url, body) {
    const response = await fetch(url, {credentials: 'same-origin', method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-CSRFToken': csrf}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('The server returned an unexpected response. Refresh the page and try again.'); }
    if (!response.ok || data.success === false) { const failure = new Error(data.error || 'This action could not be completed.'); failure.mode = data.mode; throw failure; }
    return data;
  }
  function notice(message) {
    clearTimeout(noticeTimer); $('notification').textContent = message; $('notification').hidden = false;
    noticeTimer = setTimeout(() => $('notification').hidden = true, 6500);
  }
  let speechKey = 0, audioState = {};
  const speech = window.DocuMindSpeech.create({
    synth: window.speechSynthesis, Utterance: window.SpeechSynthesisUtterance,
    onNotice: notice,
    onChange: updateAudioControls,
  });
  function updateAudioControls(playback = audioState) {
    audioState = playback;
    const availability = speech.availability();
    document.querySelectorAll('[data-listen]').forEach(button => {
      const playing = button.dataset.listen === playback.active;
      button.disabled = !availability.available;
      button.setAttribute('aria-pressed', String(playing));
      button.title = availability.reason;
      button.innerHTML = icon(playing ? 'stop' : 'listen') + (playing ? 'Stop Audio' : 'Listen');
      const turn = button.closest('.turn');
      turn.classList.toggle('is-speaking', playing);
      const status = turn.querySelector('.audio-status');
      status.textContent = playing ? `${playback.phase === 'starting' ? 'Preparing audio' : 'Reading answer aloud'} · local device voice` : availability.available ? '' : availability.reason;
      status.hidden = !status.textContent;
    });
  }
  window.addEventListener('pagehide', () => speech.stop());
  function setProfile(name) { $('profile-name').textContent = name; $('profile-initial').textContent = name.charAt(0).toUpperCase(); $('display-name').value = name; }
  setProfile(initial.display_name);
  $('workspace-id').textContent = initial.workspace_key;
  $('connection-status').innerHTML = `<i></i>${initial.gemini_configured ? 'API key configured' : 'Source retrieval mode'}`;

  function themePreference() { try { const saved = localStorage.getItem('documind-theme'); return ['light', 'dark', 'system'].includes(saved) ? saved : 'light'; } catch (_) { return 'light'; } }
  function applyTheme(choice) {
    $('theme-select').value = choice;
    $('sidebar-theme').value = choice;
    document.documentElement.dataset.theme = choice === 'system' ? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light') : choice;
  }
  applyTheme(themePreference());
  ['theme-select', 'sidebar-theme'].forEach(id => $(id).addEventListener('change', e => { try { localStorage.setItem('documind-theme', e.target.value); } catch (_) {} applyTheme(e.target.value); }));
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (themePreference() === 'system') applyTheme('system'); });

  function toggleSidebar(open) {
    $('sidebar').classList.toggle('open', open); $('sidebar-scrim').hidden = !open; $('menu-toggle').setAttribute('aria-expanded', String(open));
  }
  $('menu-toggle').addEventListener('click', () => toggleSidebar(!$('sidebar').classList.contains('open')));
  $('sidebar-scrim').addEventListener('click', () => toggleSidebar(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { toggleSidebar(false); $('source-panel').hidden = true; } });
  document.querySelectorAll('[data-close-dialog]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
  document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', e => { if (e.target === dialog) { const r = dialog.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close(); } }));

  function renderDocuments() {
    const filter = $('doc-search').value.trim().toLocaleLowerCase();
    $('doc-count').textContent = state.documents.length;
    $('doc-library').innerHTML = state.documents.filter(doc => doc.title.toLocaleLowerCase().includes(filter)).map(doc => {
      const ready = doc.status === 'ready', active = activeStatuses.includes(doc.status);
      const meta = ready ? `${doc.chunk_count} chunks${doc.file_type === 'pdf' ? ` · ${doc.page_count} pages` : ' · Text document'}` : ({needs_reindex: 'Model changed · Reindex required', failed: 'Processing failed', queued: 'Waiting to process…', extracting: 'Extracting text / OCR if needed…', embedding: 'Preparing semantic embeddings…', indexing: 'Saving vector index…'}[doc.status] || doc.status);
      return `<article class="doc-item ${state.selected.has(doc.id) ? 'selected' : ''}"><input type="checkbox" class="doc-check" data-select-doc="${doc.id}" aria-label="Select ${escape(doc.title)}" ${state.selected.has(doc.id) ? 'checked' : ''} ${ready ? '' : 'disabled'}><span class="file-badge ${doc.file_type}">${doc.file_type.toUpperCase()}</span><div class="doc-info"><div class="doc-name" title="${escape(doc.title)}">${escape(doc.title)}</div><div class="doc-meta">${escape(meta)}</div>${active ? `<progress max="100" value="${doc.progress}" aria-label="Indexing progress"></progress>` : ''}${doc.error ? `<div class="doc-error">${escape(doc.error)}</div>` : ''}<div class="doc-actions"><a href="${doc.url}" target="_blank" rel="noopener" title="Open original document">Open</a>${ready ? `<button data-summary="${doc.id}">Summarize</button>` : ''}${['failed','needs_reindex'].includes(doc.status) ? `<button data-reindex="${doc.id}">Retry indexing</button>` : ''}<button class="danger" data-delete-doc="${doc.id}" ${active ? 'disabled' : ''} aria-label="Delete ${escape(doc.title)}">Delete</button></div><div class="doc-meta" title="Uploaded ${escape(new Date(doc.uploaded_at).toLocaleString())}">${new Date(doc.uploaded_at).toLocaleDateString(undefined, {month:'short', day:'numeric'})}</div></div></article>`;
    }).join('') || `<p class="empty-hint">${state.documents.length ? 'No matching documents.' : 'A home for your next good read.<br>Upload a document to begin.'}</p>`;
    renderScope(); updateRegenerateControls();
  }
  function updateRegenerateControls() {
    const ready = new Set(state.documents.filter(d => d.status === 'ready').map(d => d.id));
    document.querySelectorAll('[data-regenerate]').forEach(button => {
      const available = JSON.parse(button.dataset.documents).every(id => ready.has(id));
      button.disabled = state.busy || !available;
      button.title = available ? "Ask again using this answer's original document selection; adds a new answer" : 'An original document was removed or needs indexing.';
    });
  }
  function renderScope() {
    const selected = state.documents.filter(d => state.selected.has(d.id));
    $('general-chat-toggle').checked = state.chatMode === 'general';
    $('scope-label').innerHTML = state.chatMode === 'general' ? `${icon('chat')} General chat` : `${icon('doc')} Active Sources`;
    $('scope-chips').innerHTML = state.chatMode === 'general'
      ? '<span class="empty-hint" style="padding:0">Uses general knowledge, not uploaded documents</span>'
      : selected.map(doc => `<button class="scope-chip" data-remove-scope="${doc.id}" title="Remove ${escape(doc.title)} from selection"><span>${escape(doc.title)}</span><b>×</b></button>`).join('') || '<span class="empty-hint" style="padding:0">Select a ready document in the library</span>';
    $('scope-count').textContent = state.chatMode === 'general' ? 'No sources' : selected.length ? `${selected.length} selected` : '';
    $('send-btn').disabled = state.busy || state.chatMode === 'documents' && !selected.length;
    $('send-btn').innerHTML = state.busy ? '<span class="spinner"></span><span>Thinking…</span>' : icon('arrow') + `<span>${state.chatMode === 'general' ? 'Send Message' : 'Ask Question'}</span>`;
    $('question-input').placeholder = state.chatMode === 'general' ? 'Message OWN GPT… (Press Enter to send)' : 'Ask anything about your documents… (Press Enter to send)';
    $('question-input-label').textContent = state.chatMode === 'general' ? 'Message OWN GPT' : 'Ask about your documents';
    $('composer-note').firstElementChild.textContent = state.chatMode === 'general'
      ? 'General chat uses Gemini and is not grounded in your uploaded documents.'
      : 'Evidence citations stay attached to answers. Verify with original sources.';
  }
  $('doc-search').addEventListener('input', renderDocuments);
  $('doc-library').addEventListener('change', e => {
    const id = Number(e.target.dataset.selectDoc); if (!id) return;
    if (e.target.checked) state.selected.add(id); else state.selected.delete(id); renderDocuments();
  });
  $('scope-chips').addEventListener('click', e => { const button = e.target.closest('[data-remove-scope]'); if (button) { state.selected.delete(Number(button.dataset.removeScope)); renderDocuments(); } });
  $('doc-library').addEventListener('click', async e => {
    const button = e.target.closest('button'); if (!button || button.disabled) return;
    const id = Number(button.dataset.deleteDoc || button.dataset.reindex || button.dataset.summary);
    if (state.busy) { notice('Wait for the current answer before changing documents.'); return; }
    try {
      if (button.dataset.deleteDoc) {
        if (!confirm('Delete this document, its original file and its indexed vectors? Saved answers will keep their historical source excerpts.')) return;
        button.disabled = true; await api(`/document/${id}/delete/`, {}); state.selected.delete(id); await refreshDocuments(); notice('Document and indexed vectors deleted.');
      } else if (button.dataset.reindex) {
        button.disabled = true; await api(`/document/${id}/reindex/`, {}); await refreshDocuments(); pollDocuments();
      } else if (button.dataset.summary) { newConversation(); state.selected = new Set([id]); renderDocuments(); ask('Summarize the main ideas of this document.'); }
    } catch (error) { button.disabled = false; notice(error.message); }
  });
  async function refreshDocuments() {
    const data = await api('/documents/');
    const previouslyReady = new Set(state.documents.filter(d => d.status === 'ready').map(d => d.id));
    state.documents = data.documents;
    for (const doc of data.documents) if (doc.status === 'ready' && !previouslyReady.has(doc.id)) state.selected.add(doc.id);
    const readyIds = new Set(data.documents.filter(d => d.status === 'ready').map(d => d.id));
    state.selected = new Set([...state.selected].filter(id => readyIds.has(id))); renderDocuments();
  }
  async function pollDocuments() {
    if (polling) return; polling = true;
    try {
      while (state.documents.some(doc => activeStatuses.includes(doc.status))) {
        await new Promise(resolve => setTimeout(resolve, 1400)); await refreshDocuments();
        const processing = state.documents.find(doc => activeStatuses.includes(doc.status));
        if (processing && !state.uploading) showUpload('Processing your document', `${processing.title} · ${processing.status === 'embedding' ? 'Loading the model / generating embeddings. First use can take a few minutes.' : processing.status}`, processing.progress);
      }
      if (!state.uploading) $('upload-status').hidden = true;
    } catch (error) { notice(error.message); $('upload-status').hidden = true; }
    finally { polling = false; }
  }
  function showUpload(title, detail, progress) { $('upload-title').textContent = title; $('upload-detail').textContent = detail; $('upload-progress').value = progress; $('upload-status').hidden = false; }
  async function uploadFiles(files) {
    if (state.uploading) { notice('An upload is already in progress.'); return; }
    const selected = [...files]; if (!selected.length) return;
    state.uploading = true;
    for (const file of selected) {
      if (!/\.(pdf|txt)$/i.test(file.name) || !file.size || file.size > 15 * 1024 * 1024) { notice('Choose a non-empty PDF or TXT file up to 15 MB.'); continue; }
      try {
        showUpload('Uploading your document', file.name, 0);
        const result = await new Promise((resolve, reject) => {
          const xhr = new XMLHttpRequest(); xhr.open('POST', '/upload/'); xhr.setRequestHeader('X-CSRFToken', csrf); xhr.responseType = 'json';
          xhr.upload.onprogress = e => { if (e.lengthComputable) showUpload(`Uploading · ${Math.round(e.loaded / e.total * 100)}%`, file.name, e.loaded / e.total * 100); };
          xhr.upload.onload = () => showUpload('Upload sent · waiting for server', file.name, 0);
          xhr.onload = () => { const data = xhr.response; if (xhr.status >= 200 && xhr.status < 300 && data?.success) resolve(data); else reject(new Error(data?.error || 'Upload failed. Please try again.')); };
          xhr.onerror = () => reject(new Error('The upload could not reach the server.'));
          const form = new FormData(); form.append('document', file); xhr.send(form);
        });
        const doc = result.document; const index = state.documents.findIndex(d => d.id === doc.id);
        if (index < 0) state.documents.unshift(doc); else state.documents[index] = doc;
        if (doc.status === 'ready') state.selected.add(doc.id); renderDocuments();
        if (result.duplicate) notice('This document is already in your library.');
      } catch (error) { notice(error.message); }
    }
    state.uploading = false; $('file-input').value = ''; $('upload-status').hidden = true; pollDocuments();
  }
  document.querySelectorAll('[data-upload]').forEach(button => button.addEventListener('click', () => $('file-input').click()));
  $('drop-zone').addEventListener('click', () => $('file-input').click());
  $('file-input').addEventListener('change', e => uploadFiles(e.target.files));
  for (const event of ['dragenter','dragover']) $('drop-zone').addEventListener(event, e => { e.preventDefault(); $('drop-zone').classList.add('dragging'); });
  for (const event of ['dragleave','drop']) $('drop-zone').addEventListener(event, e => { e.preventDefault(); $('drop-zone').classList.remove('dragging'); });
  $('drop-zone').addEventListener('drop', e => uploadFiles(e.dataTransfer.files));

  function renderConversations() {
    $('conversation-list').innerHTML = state.conversations.map(c => `<button class="conversation-item ${c.id === state.conversation ? 'active' : ''}" data-conversation="${c.id}" title="${escape(c.title)}">${icon('chat')}<span>${escape(c.title)}</span></button>`).join('') || '<p class="empty-hint">Your next conversation starts here.</p>';
    $('conversation-menu-btn').disabled = !state.conversation || state.busy;
    $('conversation-title').textContent = state.conversations.find(c => c.id === state.conversation)?.title || 'New conversation';
  }
  async function refreshConversations() { const data = await api('/conversations/'); state.conversations = data.conversations; renderConversations(); }
  function newConversation() {
    if (state.busy) { notice('Wait for the current answer to finish.'); return false; }
    speech.stop();
    state.conversation = null; $('chat-messages').replaceChildren(); $('chat-messages').hidden = true; $('welcome-screen').hidden = false; $('source-panel').hidden = true; $('question-input').value = ''; $('question-input').style.height = 'auto'; renderConversations(); toggleSidebar(false); return true;
  }
  $('new-chat-btn').addEventListener('click', newConversation);
  $('conversation-list').addEventListener('click', async e => {
    const button = e.target.closest('[data-conversation]'); if (!button || state.busy) return;
    try {
      const data = await api(`/conversation/${button.dataset.conversation}/`);
      speech.stop();
      state.conversation = data.conversation.id;
      state.chatMode = data.chat_mode === 'general' ? 'general' : 'documents';
      $('general-chat-toggle').checked = state.chatMode === 'general';
      const ready = new Set(state.documents.filter(d => d.status === 'ready').map(d => d.id));
      state.selected = new Set(data.conversation.documents.filter(id => ready.has(id)));
      $('chat-messages').replaceChildren(); $('welcome-screen').hidden = true; $('chat-messages').hidden = false; $('source-panel').hidden = true;
      data.turns.forEach(turn => appendTurn(turn)); renderDocuments(); renderConversations(); toggleSidebar(false); scrollBottom();
    } catch (error) { notice(error.message); }
  });
  async function clearHistory() {
    if (state.busy || !confirm('Permanently delete all conversations in this guest workspace? Your documents will stay in the library.')) return;
    try { await api('/history/clear/', {}); state.conversations = []; newConversation(); notice('Conversation history deleted.'); } catch (error) { notice(error.message); }
  }
  $('clear-history-btn').addEventListener('click', clearHistory); $('settings-clear-history').addEventListener('click', clearHistory);
  $('conversation-menu-btn').addEventListener('click', () => { $('rename-title').value = state.conversations.find(c => c.id === state.conversation)?.title || ''; $('conversation-dialog').showModal(); });
  $('rename-form').addEventListener('submit', async e => { e.preventDefault(); try { await api(`/conversation/${state.conversation}/rename/`, {title: $('rename-title').value}); await refreshConversations(); $('conversation-dialog').close(); } catch (error) { notice(error.message); } });
  for (const action of ['clear','delete']) $(`${action}-conversation-btn`).addEventListener('click', async () => {
    if (!confirm(action === 'delete' ? 'Permanently delete this conversation?' : 'Clear all messages in this conversation?')) return;
    try { await api(`/conversation/${state.conversation}/${action}/`, {}); $('conversation-dialog').close(); newConversation(); await refreshConversations(); } catch (error) { notice(error.message); }
  });
  $('settings-btn').addEventListener('click', async () => {
    $('settings-dialog').showModal();
    try { const data = await api('/api/stats/'); $('stats-content').innerHTML = '<dl>' + [['Documents', data.total_documents], ['PDF pages', data.total_pages], ['Indexed chunks', data.total_chunks], ['Saved questions', data.total_queries], ['Embedding model', data.embedding_model], ['Vector store', data.vector_store], ['Generation model', data.ai_model], ['API status', data.gemini_configured ? 'Key configured · availability checked when asking' : 'Key not configured']].map(([label, value]) => `<dt>${escape(label)}</dt><dd>${escape(value)}</dd>`).join('') + '</dl>'; } catch (error) { $('stats-content').textContent = error.message; }
  });
  $('profile-form').addEventListener('submit', async e => { e.preventDefault(); try { const data = await api('/profile/', {display_name: $('display-name').value}); setProfile(data.display_name); notice('Display name saved.'); } catch (error) { notice(error.message); } });

  function formatAnswer(text, sourceCount) {
    const blocks = text.split(/```/); let html = '';
    const inline = value => escape(value).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\[\s*Source\s+(\d+)\s*\]/gi, (match, number) => Number(number) > 0 && Number(number) <= sourceCount ? `<button class="inline-citation" data-source="${Number(number)-1}" aria-label="Preview source ${number}">${number}</button>` : match);
    blocks.forEach((block, index) => {
      if (index % 2) { html += `<pre><code>${escape(block.replace(/^\w+\n/, ''))}</code></pre>`; return; }
      let list = '';
      for (const line of block.split('\n')) {
        const bullet = /^\s*(?:[-*]|\d+\.)\s+(.+)$/.exec(line);
        if (bullet) { if (!list) { html += '<ul>'; list = 'ul'; } html += `<li>${inline(bullet[1])}</li>`; }
        else { if (list) { html += '</ul>'; list = ''; } if (/^#{1,4}\s/.test(line)) html += `<h3>${inline(line.replace(/^#{1,4}\s+/, ''))}</h3>`; else if (line.trim()) html += `<p>${inline(line)}</p>`; }
      }
      if (list) html += '</ul>';
    }); return html;
  }
  function sourceMeta(source) { return source.file_type !== 'txt' && source.page ? `Page ${source.page} · Chunk ${source.chunk_index}` : `${source.file_type === 'txt' ? 'TXT · ' : ''}Chunk ${source.chunk_index}`; }
  function previewSource(source) {
    $('source-preview').innerHTML = `<span class="file-badge ${escape(source.file_type)}">${escape((source.file_type || 'doc').toUpperCase())}</span><h3 class="preview-file">${escape(source.title)}</h3><p class="preview-meta">${escape(sourceMeta(source))}</p><blockquote>${escape(source.text)}</blockquote>${source.url ? `<a href="${escape(source.url)}" target="_blank" rel="noopener">Open original${source.page ? ` · Page ${source.page}` : ''} ↗</a>` : ''}${source.unavailable ? '<small>The original file has been removed. This saved source excerpt is still available.</small>' : ''}<small>This is the original retrieved passage, kept in its original language. ${source.score == null ? 'Selected for excerpt coverage.' : `Cosine similarity: ${source.score.toFixed(4)}. Similarity is a retrieval measure, not a confidence guarantee.`}</small>`;
    $('source-panel').hidden = false;
  }
  $('close-source').addEventListener('click', () => $('source-panel').hidden = true);
  function sourceCards(sources) {
    return `<div class="sources-block"><div class="sources-label">${icon('book')} Source passages <span>${sources.length} retrieved excerpt${sources.length === 1 ? '' : 's'}</span></div><div class="source-grid">${sources.map((s, i) => `<details class="source-card"><summary><strong>${i+1}. ${escape(s.title)}</strong><small>${escape(sourceMeta(s))}${s.score == null ? ' · Coverage sample' : ` · Similarity ${s.score.toFixed(3)}`}</small><div class="source-snippet">${escape(s.text)}</div></summary><div class="source-excerpt">${escape(s.text)}</div><div class="source-links"><button data-source="${i}">Preview passage</button>${s.url ? `<a href="${escape(s.url)}" target="_blank" rel="noopener">Open original ↗</a>` : ''}</div></details>`).join('')}</div></div>`;
  }
  function appendTurn(data, target) {
    const turn = target || document.createElement('article'); turn.className = 'turn';
    const sources = data.sources || [];
    const audioKey = String(++speechKey);
    const originalDocuments = data.query_metadata?.documents;
    const canRegenerate = Array.isArray(originalDocuments) && originalDocuments.length > 0 && ['gemini', 'no_evidence', 'retrieval_only'].includes(data.mode);
    const modes = {chat:'General chat · Gemini', gemini:'Answer with document evidence', no_evidence:'Insufficient evidence', retrieval_only:'Source passages · generation unavailable', provider_error:'AI generation error', retrieval_failure:'Retrieval error', validation_error:'Check your request', processing:'Document processing', busy:'Request in progress', network_error:'Connection error'};
    turn.innerHTML = `<div class="user-message"><div class="user-bubble">${escape(data.question)}</div></div><div class="assistant-heading"><span class="assistant-mark">${icon('doc')}</span> OWN GPT <span class="mode-label ${['provider_error','retrieval_failure'].includes(data.mode) ? 'warning' : ''}">${escape(modes[data.mode] || data.mode)}</span></div><div class="answer-text">${formatAnswer(data.answer, sources.length)}</div>${sources.length ? sourceCards(sources) : ''}${data.query_metadata?.scope_note && sources.length ? `<p class="scope-note">${escape(data.query_metadata.scope_note)}${data.query_metadata.summary ? ' Longer documents are sampled across their content.' : ''}</p>` : ''}<div class="answer-tools" role="group" aria-label="Answer actions"><button data-listen="${audioKey}" aria-pressed="false" aria-describedby="audio-status-${audioKey}">${icon('listen')}Listen</button><button data-copy title="Copy the answer text">${icon('copy')}Copy Answer</button><button data-view-sources ${sources.length ? '' : 'disabled'} aria-expanded="false" title="${sources.length ? 'Expand the retrieved passages for this answer' : 'No sources were retrieved for this answer'}">${icon('book')}View Sources</button>${canRegenerate ? `<button data-regenerate data-documents="${escape(JSON.stringify(originalDocuments))}" title="Ask again using this answer's original document selection; adds a new answer">${icon('refresh')}Regenerate Answer</button>` : ''}<button data-export title="Download this answer and its source passages">${icon('download')}Export</button>${data.created_at ? `<time datetime="${escape(data.created_at)}">${new Date(data.created_at).toLocaleTimeString(undefined, {hour:'2-digit', minute:'2-digit'})}</time>` : ''}</div><p class="audio-status" id="audio-status-${audioKey}" role="status" hidden></p>`;
    turn.addEventListener('click', async e => {
      const source = e.target.closest('[data-source]'); if (source) { previewSource(sources[Number(source.dataset.source)]); return; }
      if (e.target.closest('[data-copy]')) { try { await navigator.clipboard.writeText(data.answer); notice('Answer copied.'); } catch (_) { notice('Clipboard unavailable. Select the answer text to copy it.'); } }
      if (e.target.closest('[data-listen]')) speech.play(audioKey, data.answer, data.query_metadata?.language_hint);
      const viewSources = e.target.closest('[data-view-sources]');
      if (viewSources && sources.length) {
        const open = viewSources.getAttribute('aria-expanded') !== 'true';
        turn.querySelectorAll('.source-card').forEach(card => card.open = open);
        viewSources.setAttribute('aria-expanded', String(open));
        viewSources.innerHTML = icon('book') + (open ? 'Hide Sources' : 'View Sources');
        if (open) turn.querySelector('.sources-block').scrollIntoView({block: 'nearest'});
      }
      if (e.target.closest('[data-regenerate]') && canRegenerate && !state.busy) {
        const ready = new Set(state.documents.filter(d => d.status === 'ready').map(d => d.id));
        if (!originalDocuments.every(id => ready.has(id))) { notice('An original document was removed or needs indexing. Select ready documents and ask a new question.'); return; }
        state.selected = new Set(originalDocuments); renderDocuments();
        ask(data.question);
      }
      if (e.target.closest('[data-export]')) {
        let content = `# OWN GPT\n\n## Question\n${data.question}\n\n## Answer\n${data.answer}\n\n`;
        sources.forEach((source, i) => content += `### Source ${i+1}: ${source.title} · ${sourceMeta(source)}\n\n${source.text}\n\n`);
        const url = URL.createObjectURL(new Blob([content], {type:'text/markdown;charset=utf-8'})); const link = document.createElement('a'); link.href = url; link.download = 'own-gpt-answer.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 500);
      }
    });
    if (!target) $('chat-messages').appendChild(turn);
    updateAudioControls(); updateRegenerateControls(); return turn;
  }
  function scrollBottom() { requestAnimationFrame(() => { $('message-scroll').scrollTop = $('message-scroll').scrollHeight; }); }
  function setBusy(busy) { state.busy = busy; $('question-input').readOnly = busy; $('general-chat-toggle').disabled = busy; $('question-form').setAttribute('aria-busy', String(busy)); updateRegenerateControls(); document.querySelectorAll('.doc-check').forEach(input => input.disabled = busy || state.documents.find(d => d.id === Number(input.dataset.selectDoc))?.status !== 'ready'); renderScope(); renderConversations(); }
  async function ask(question) {
    question = question.trim(); if (!question || state.busy) return;
    if (state.chatMode === 'documents' && !state.selected.size) { notice('Select a ready document or switch to General Chat.'); return; }
    speech.stop();
    setBusy(true); $('welcome-screen').hidden = true; $('chat-messages').hidden = false;
    const pending = document.createElement('article'); pending.className = 'turn'; pending.innerHTML = `<div class="user-message"><div class="user-bubble">${escape(question)}</div></div><div class="loading-message"><span class="spinner"></span><span>${state.chatMode === 'general' ? 'Thinking…' : 'Reading your sources and preparing an answer…'}</span></div><div class="skeleton-lines" aria-hidden="true"><span></span><span></span><span></span></div>`;
    $('chat-messages').appendChild(pending); $('question-input').value = ''; $('question-input').style.height = 'auto'; scrollBottom();
    try {
      const requestId = crypto.randomUUID();
      const data = await api('/ask/', {question, chat_mode:state.chatMode, documents:state.chatMode === 'general' ? [] : [...state.selected], conversation_id:state.conversation, request_id:requestId});
      state.conversation = data.conversation_id; appendTurn(data, pending); await refreshConversations();
    } catch (error) { appendTurn({question, answer:error.message, sources:[], mode:error.mode || 'network_error'}, pending); }
    finally { setBusy(false); scrollBottom(); $('question-input').focus(); }
  }
  $('general-chat-toggle').addEventListener('change', e => {
    state.chatMode = e.target.checked ? 'general' : 'documents';
    renderScope();
  });
  $('question-form').addEventListener('submit', e => { e.preventDefault(); ask($('question-input').value); });
  $('question-input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask($('question-input').value); } });
  $('question-input').addEventListener('input', e => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px'; });
  document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { $('question-input').value = button.dataset.question; $('question-input').focus(); }));
  renderDocuments(); renderConversations(); pollDocuments();
})();
