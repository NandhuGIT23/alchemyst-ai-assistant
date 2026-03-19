/*!
 * widget.js — embeddable dark chat widget
 * Drop this one line on any page to activate:
 * <script src="https://your-cdn.com/widget.js" data-api="https://your-api.railway.app"></script>
 */
(function () {
  const API_BASE =
    document.currentScript?.getAttribute("data-api") || "http://localhost:8000";
  const BOT_NAME =
    document.currentScript?.getAttribute("data-name") || "Assistant";

  // ── Inject styles ────────────────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = `
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500&family=DM+Mono:wght@400&display=swap');
  
      #_chatroot * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'DM Sans', sans-serif; }
  
      #_chatroot {
        position: fixed;
        bottom: 28px;
        right: 28px;
        z-index: 99999;
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 12px;
      }
  
      /* ── Toggle button ── */
      #_chatbtn {
        width: 56px; height: 56px;
        border-radius: 50%;
        background: linear-gradient(135deg, #6C63FF 0%, #3ECFCF 100%);
        border: none; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 4px 24px rgba(108,99,255,0.45);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
      }
      #_chatbtn:hover { transform: scale(1.08); box-shadow: 0 6px 32px rgba(108,99,255,0.6); }
      #_chatbtn svg { transition: transform 0.3s ease; }
      #_chatbtn.open svg { transform: rotate(45deg); }
  
      /* ── Panel ── */
      #_chatpanel {
        width: 380px;
        height: 560px;
        background: #0f0f13;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 20px;
        display: flex;
        flex-direction: column;
        overflow: hidden;
        box-shadow: 0 24px 64px rgba(0,0,0,0.6);
        transform: translateY(16px) scale(0.97);
        opacity: 0;
        pointer-events: none;
        transition: transform 0.25s cubic-bezier(0.34,1.56,0.64,1), opacity 0.2s ease;
      }
      #_chatpanel.visible {
        transform: translateY(0) scale(1);
        opacity: 1;
        pointer-events: all;
      }
  
      /* ── Header ── */
      ._chatheader {
        padding: 16px 20px;
        background: #16161e;
        border-bottom: 1px solid rgba(255,255,255,0.06);
        display: flex; align-items: center; gap: 12px;
        flex-shrink: 0;
      }
      ._avatardot {
        width: 36px; height: 36px; border-radius: 50%;
        background: linear-gradient(135deg, #6C63FF, #3ECFCF);
        display: flex; align-items: center; justify-content: center;
        font-size: 16px; flex-shrink: 0;
      }
      ._headertitle { font-size: 14px; font-weight: 500; color: #f0f0f5; }
      ._headerstatus { font-size: 11px; color: #3ECFCF; display: flex; align-items: center; gap: 4px; }
      ._statusdot { width: 6px; height: 6px; border-radius: 50%; background: #3ECFCF;
        animation: _pulse 2s infinite; }
      @keyframes _pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
  
      /* ── Messages ── */
      ._chatmsgs {
        flex: 1; overflow-y: auto; padding: 20px 16px;
        display: flex; flex-direction: column; gap: 14px;
        scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent;
      }
      ._chatmsgs::-webkit-scrollbar { width: 4px; }
      ._chatmsgs::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
  
      ._msg { display: flex; gap: 8px; max-width: 100%; animation: _fadein 0.2s ease; }
      @keyframes _fadein { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:none} }
  
      ._msg.user { flex-direction: row-reverse; }
  
      ._bubble {
        padding: 10px 14px; border-radius: 16px;
        font-size: 13.5px; line-height: 1.6; max-width: 82%;
        word-break: break-word;
      }
      ._msg.bot  ._bubble { background: #1e1e2a; color: #dddde8; border-bottom-left-radius: 4px; }
      ._msg.user ._bubble { background: linear-gradient(135deg,#6C63FF,#4f4ac7); color: #fff; border-bottom-right-radius: 4px; }
  
      ._bubble strong { color: #a78bfa; }
      ._bubble em { color: #7dd3fc; }
      ._bubble code { font-family: 'DM Mono', monospace; font-size: 12px;
        background: rgba(255,255,255,0.07); padding: 1px 5px; border-radius: 4px; }
  
      /* ── Sources ── */
      ._sources { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
      ._source {
        font-size: 11px; padding: 3px 8px; border-radius: 20px;
        background: rgba(62,207,207,0.1); color: #3ECFCF;
        border: 1px solid rgba(62,207,207,0.2);
        text-decoration: none; white-space: nowrap;
        transition: background 0.15s;
      }
      ._source:hover { background: rgba(62,207,207,0.2); }
  
      /* ── Intent badge ── */
      ._intent {
        font-size: 10px; padding: 2px 7px; border-radius: 10px;
        font-weight: 500; letter-spacing: 0.5px; margin-bottom: 4px;
        display: inline-block; text-transform: uppercase;
      }
      ._intent.qa       { background: rgba(108,99,255,0.15); color: #a78bfa; }
      ._intent.schedule { background: rgba(62,207,207,0.15); color: #3ECFCF; }
      ._intent.ticket   { background: rgba(251,191,36,0.15);  color: #fbbf24; }
      ._intent.escalate { background: rgba(248,113,113,0.15); color: #f87171; }
  
      /* ── Typing indicator ── */
      ._typing { display: flex; gap: 4px; align-items: center; padding: 4px 0; }
      ._typing span {
        width: 6px; height: 6px; border-radius: 50%; background: #555;
        animation: _bounce 1.2s infinite;
      }
      ._typing span:nth-child(2) { animation-delay: 0.15s; }
      ._typing span:nth-child(3) { animation-delay: 0.3s; }
      @keyframes _bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-5px)} }
  
      /* ── Input area ── */
      ._chatinput {
        padding: 14px 16px;
        background: #16161e;
        border-top: 1px solid rgba(255,255,255,0.06);
        display: flex; gap: 10px; align-items: flex-end;
        flex-shrink: 0;
      }
      ._chatinput textarea {
        flex: 1; background: #1e1e2a; border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px; color: #f0f0f5; font-size: 13.5px;
        padding: 10px 14px; resize: none; outline: none;
        font-family: 'DM Sans', sans-serif; line-height: 1.5;
        max-height: 120px; min-height: 42px;
        transition: border-color 0.15s;
      }
      ._chatinput textarea::placeholder { color: #555; }
      ._chatinput textarea:focus { border-color: rgba(108,99,255,0.5); }
      ._sendbtn {
        width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
        background: linear-gradient(135deg,#6C63FF,#4f4ac7);
        border: none; cursor: pointer;
        display: flex; align-items: center; justify-content: center;
        transition: opacity 0.15s, transform 0.15s;
      }
      ._sendbtn:hover { opacity: 0.85; transform: scale(1.05); }
      ._sendbtn:disabled { opacity: 0.35; cursor: not-allowed; transform: none; }
  
      /* ── Welcome card ── */
      ._welcome {
        background: #1e1e2a; border-radius: 16px; padding: 16px;
        border: 1px solid rgba(108,99,255,0.2);
      }
      ._welcome h3 { font-size: 14px; color: #f0f0f5; font-weight: 500; margin-bottom: 6px; }
      ._welcome p  { font-size: 12.5px; color: #888; line-height: 1.6; }
      ._chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
      ._chip {
        font-size: 12px; padding: 5px 11px; border-radius: 20px; cursor: pointer;
        background: rgba(108,99,255,0.1); color: #a78bfa;
        border: 1px solid rgba(108,99,255,0.2);
        transition: background 0.15s;
      }
      ._chip:hover { background: rgba(108,99,255,0.2); }
  
      @media (max-width: 480px) {
        #_chatpanel { width: calc(100vw - 24px); height: 70vh; }
        #_chatroot  { right: 12px; bottom: 12px; }
      }
    `;
  document.head.appendChild(style);

  // ── Build DOM ──────────────────────────────────────────────────────────────
  const root = document.createElement("div");
  root.id = "_chatroot";
  root.innerHTML = `
      <div id="_chatpanel">
        <div class="_chatheader">
          <div class="_avatardot">✦</div>
          <div>
            <div class="_headertitle">${BOT_NAME}</div>
            <div class="_headerstatus"><span class="_statusdot"></span> Online</div>
          </div>
        </div>
        <div class="_chatmsgs" id="_chatmsgs">
          <div class="_msg bot">
            <div class="_bubble">
              <div class="_welcome">
                <h3>Hi there 👋</h3>
                <p>I can answer questions about our company, help you book a demo, raise a support ticket, or connect you with our team.</p>
                <div class="_chips">
                  <span class="_chip">What do you offer?</span>
                  <span class="_chip">Book a demo</span>
                  <span class="_chip">Report an issue</span>
                  <span class="_chip">Talk to someone</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="_chatinput">
          <textarea id="_chattext" placeholder="Ask me anything…" rows="1"></textarea>
          <button class="_sendbtn" id="_sendbtn" disabled>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
  
      <button id="_chatbtn" title="Chat with us">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
      </button>
    `;
  document.body.appendChild(root);

  // ── State ──────────────────────────────────────────────────────────────────
  let sessionId = "sess_" + Math.random().toString(36).slice(2);
  let isOpen = false;
  let isStreaming = false;

  const panel = root.querySelector("#_chatpanel");
  const btn = root.querySelector("#_chatbtn");
  const msgs = root.querySelector("#_chatmsgs");
  const textarea = root.querySelector("#_chattext");
  const sendBtn = root.querySelector("#_sendbtn");

  // ── Toggle panel ───────────────────────────────────────────────────────────
  btn.addEventListener("click", () => {
    isOpen = !isOpen;
    panel.classList.toggle("visible", isOpen);
    btn.classList.toggle("open", isOpen);
    if (isOpen) setTimeout(() => textarea.focus(), 300);
  });

  // ── Chip clicks ────────────────────────────────────────────────────────────
  msgs.addEventListener("click", (e) => {
    if (e.target.classList.contains("_chip")) {
      textarea.value = e.target.textContent;
      sendBtn.disabled = false;
      sendMessage();
    }
  });

  // ── Textarea auto-resize + enable send ────────────────────────────────────
  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + "px";
    sendBtn.disabled = !textarea.value.trim() || isStreaming;
  });

  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) sendMessage();
    }
  });

  sendBtn.addEventListener("click", sendMessage);

  // ── Render helpers ─────────────────────────────────────────────────────────
  function appendMsg(role, html, intentBadge = null) {
    const div = document.createElement("div");
    div.className = `_msg ${role}`;

    const badge = intentBadge
      ? `<div class="_intent ${intentBadge}">${intentBadge}</div>`
      : "";

    div.innerHTML = `<div class="_bubble">${badge}${html}</div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div.querySelector("._bubble");
  }

  function showTyping() {
    const div = document.createElement("div");
    div.className = "_msg bot";
    div.id = "_typing";
    div.innerHTML = `<div class="_bubble"><div class="_typing"><span></span><span></span><span></span></div></div>`;
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function removeTyping() {
    document.getElementById("_typing")?.remove();
  }

  // Minimal markdown: **bold**, *italic*, `code`, newlines
  function renderMarkdown(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/`(.+?)`/g, "<code>$1</code>")
      .replace(/\n/g, "<br>");
  }

  // ── Send message ───────────────────────────────────────────────────────────
  async function sendMessage() {
    const question = textarea.value.trim();
    if (!question || isStreaming) return;

    textarea.value = "";
    textarea.style.height = "auto";
    sendBtn.disabled = true;
    isStreaming = true;

    // Render user message
    appendMsg("user", renderMarkdown(question));

    // Show typing
    showTyping();

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: sessionId }),
      });

      if (!response.ok) throw new Error(`Server error ${response.status}`);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let botBubble = null;
      let fullText = "";
      let intentSeen = null;

      // Parse SSE stream
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split("\n\n");
        buffer = parts.pop(); // keep incomplete chunk

        for (const part of parts) {
          const eventLine = part.match(/^event: (.+)$/m)?.[1];
          const dataLine = part.match(/^data: (.+)$/m)?.[1];
          if (!dataLine) continue;

          let payload;
          try {
            payload = JSON.parse(dataLine);
          } catch {
            continue;
          }

          if (eventLine === "intent") {
            intentSeen = payload.intent;
          }

          if (eventLine === "token") {
            if (!botBubble) {
              removeTyping();
              botBubble = appendMsg("bot", "", intentSeen);
              fullText = "";
            }
            fullText += payload.text;
            botBubble.innerHTML =
              (intentSeen
                ? `<div class="_intent ${intentSeen}">${intentSeen}</div>`
                : "") + renderMarkdown(fullText);
            msgs.scrollTop = msgs.scrollHeight;
          }

          if (eventLine === "done" && payload.sources?.length) {
            const sourcesHtml = payload.sources
              .slice(0, 4)
              .map(
                (s) =>
                  `<a class="_source" href="${s.url}" target="_blank">↗ ${
                    s.title || s.url
                  }</a>`
              )
              .join("");
            const sourceDiv = document.createElement("div");
            sourceDiv.className = "_sources";
            sourceDiv.innerHTML = sourcesHtml;
            botBubble?.appendChild(sourceDiv);
          }

          if (eventLine === "error") {
            removeTyping();
            appendMsg("bot", "⚠ Something went wrong. Please try again.");
          }
        }
      }
    } catch (err) {
      removeTyping();
      appendMsg("bot", `⚠ Could not reach the server. Please try again.`);
    }

    isStreaming = false;
    sendBtn.disabled = false;
    textarea.focus();
  }
})();
