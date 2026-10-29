let walletAddress = null;
let lastVerified = null;
let verificationId = null;
let conversationId = localStorage.getItem("conversationId") || null;
let requestInFlight = false;
let stepTimers = [];

document.addEventListener("DOMContentLoaded", function () {
  initEventListeners();
  restoreWalletState();
  restoreChatHistory();
  updateExampleCardsState();
});

function initEventListeners() {
  const input = document.getElementById("prompt-input");
  if (input) {
    input.addEventListener("paste", function () {
      setTimeout(() => autoResize(this), 0);
    });
  }
  document.addEventListener(
    "wheel",
    function (e) {
      if (e.target.closest(".input-shell")) {
        e.target.blur();
      }
    },
    true,
  );
}

function restoreWalletState() {
  const savedAddress = localStorage.getItem("walletAddress");
  if (savedAddress && window.ethereum) {
    walletAddress = savedAddress;
    renderConnectedWallet();
  }
}

function renderConnectedWallet(btn = document.getElementById("wallet-btn")) {
  const short = walletAddress.slice(0, 6) + "…" + walletAddress.slice(-4);
  btn.classList.add("connected");
  btn.innerHTML = `<div class="wallet-dot"></div><span>${esc(short)}</span>`;
}

function restoreChatHistory() {
  const saved = localStorage.getItem("chatHistory");
  if (saved) {
    try {
      const messages = JSON.parse(saved);
      if (messages.length > 0) {
        showChat();
        messages.forEach((msg) => {
          if (msg.type === "user") {
            appendRow(
              `
    <div class="bubble-wrap user">
      <div class="bubble">${esc(msg.text)}</div>
    </div>`,
              true,
            );
          } else if (msg.text) {
            appendRow(
              `
    <div class="ai-avatar" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
        <path d="M12 2l2.09 6.26L20 10l-5.91 1.74L12 18l-2.09-5.26L4 11l5.91-1.74L12 2z" fill="white"/>
      </svg>
    </div>
    <div class="bubble-wrap ai">
      <div class="bubble">${esc(msg.text)}</div>
    </div>`,
              false,
            );
          }
        });
      }
    } catch (e) {
      console.error("Failed to restore chat history:", e);
    }
  }
}

function saveChatMessage(type, content) {
  const saved = localStorage.getItem("chatHistory") || "[]";
  try {
    const messages = JSON.parse(saved);
    const holder = document.createElement("div");
    holder.innerHTML = content;
    messages.push({
      type,
      text: type === "user" ? content : (holder.textContent || "").trim().slice(0, 2000),
    });
    if (messages.length > 50) {
      messages.shift();
    }
    localStorage.setItem("chatHistory", JSON.stringify(messages));
  } catch (e) {
    console.error("Failed to save chat message:", e);
  }
}

function clearChatHistory() {
  localStorage.setItem("chatHistory", "[]");
  const cc = document.getElementById("chat-container");
  if (cc) {
    cc.innerHTML = "";
  }
}

function updateExampleCardsState() {
  const cards = document.querySelectorAll(".ex-card");
  cards.forEach((card) => {
    card.style.opacity = "1";
    card.style.cursor = "pointer";
    card.style.pointerEvents = "auto";
    card.classList.remove("disabled");
  });
}

async function connectWallet() {
  if (!window.ethereum) {
    showErrToast("🦊 MetaMask not found — please install it from metamask.io");
    return;
  }
  const btn = document.getElementById("wallet-btn");
  const label = document.getElementById("wallet-label");

  if (walletAddress) {
    walletAddress = null;
    localStorage.removeItem("walletAddress");
    btn.classList.remove("connected");
    btn.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="7" width="20" height="14" rx="2.5"/><path d="M16 14h.01"/><path d="M2 10h20"/></svg><span>Connect Wallet</span>`;
    updateExampleCardsState();
    clearChatHistory();
    const ws = document.getElementById("welcome-screen");
    const cc = document.getElementById("chat-container");
    if (ws) ws.style.display = "flex";
    if (cc) cc.style.display = "none";
    return;
  }

  label.textContent = "Connecting…";
  try {
    await window.ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: "0xaa36a7" }],
    });
    const provider = new ethers.providers.Web3Provider(window.ethereum);
    await provider.send("eth_requestAccounts", []);
    const signer = provider.getSigner();
    walletAddress = await signer.getAddress();
    localStorage.setItem("walletAddress", walletAddress);
    renderConnectedWallet(btn);
    updateExampleCardsState();
  } catch (e) {
    label.textContent = "Connect Wallet";
    showErrToast("⚠️ Wallet connection failed: " + e.message);
  }
}

function handleInputKey(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

function autoResize(el) {
  el.style.height = "auto";
  const newHeight = Math.min(el.scrollHeight, 120);
  el.style.height = newHeight + "px";
}

function quick(text) {
  const el = document.getElementById("prompt-input");
  if (!el) {
    alert("⚠️ Input field is not ready yet. Please try again in a moment.");
    return;
  }
  el.value = text;
  autoResize(el);
  el.focus();
  setTimeout(() => send(), 100);
}

function showChat() {
  const ws = document.getElementById("welcome-screen");
  const cc = document.getElementById("chat-container");

  ws.style.animation = "fadeUp 0.4s ease reverse backwards";
  setTimeout(() => {
    ws.style.display = "none";
  }, 150);

  cc.style.display = "flex";
  cc.style.flexDirection = "column";
  cc.style.opacity = "0";
  cc.offsetHeight; // Trigger reflow
  cc.style.transition = "opacity 0.3s ease";
  cc.style.opacity = "1";
}

function appendRow(innerHtml, isUser) {
  const cc = document.getElementById("chat-container");
  const row = document.createElement("div");
  row.className = "msg-row" + (isUser ? " user" : "");
  row.innerHTML = innerHtml;
  row.style.opacity = "0";
  row.style.animation = "fadeUp 0.3s ease forwards";
  cc.appendChild(row);

  requestAnimationFrame(() => {
    cc.scrollTop = cc.scrollHeight;
  });

  return row;
}

function addUserMsg(text) {
  const html = `
    <div class="bubble-wrap user">
      <div class="bubble">${esc(text)}</div>
    </div>`;
  saveChatMessage("user", text);
  return appendRow(html, true);
}

function addAIMsg(html, id) {
  const fullHtml = `
    <div class="ai-avatar" aria-hidden="true">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
        <path d="M12 2l2.09 6.26L20 10l-5.91 1.74L12 18l-2.09-5.26L4 11l5.91-1.74L12 2z" fill="white"/>
      </svg>
    </div>
    <div class="bubble-wrap ai">
      <div class="bubble" ${id ? `id="${id}"` : ""}>${html}</div>
    </div>`;
  saveChatMessage("ai", html);
  return appendRow(fullHtml, false);
}

function esc(t) {
  const div = document.createElement("div");
  div.textContent = String(t);
  return div.innerHTML;
}

function showErrToast(msg) {
  addAIMsg(`<div style="display:flex;align-items:flex-start;gap:9px;color:#7F1D1D;font-size:14px;line-height:1.5;">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#EF4444" stroke-width="2" style="flex-shrink:0;margin-top:2px">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12.01" y1="16" x2="12" y2="16"/>
    </svg><span>${esc(msg)}</span></div>`);
}

const STEPS = [
  {
    label: "Understanding intent",
    sub: "Parsing your natural language request",
  },
  {
    label: "Verifying with Knowledge Graph",
    sub: "Checking protocol relationships",
  },
  {
    label: "Preparing smart wallet transaction",
    sub: "Building ERC-4337 user operation",
  },
];

const STEP_ICONS = [
  /* sparkle */ `<svg width="13" height="13" viewBox="0 0 24 24" fill="FILL"><path d="M12 2l2.09 6.26L20 10l-5.91 1.74L12 18l-2.09-5.26L4 11l5.91-1.74L12 2z"/></svg>`,
  /* graph   */ `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="FILL" stroke-width="2.5"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><path d="M7 11.5l10-5M7 12.5l10 5"/></svg>`,
  /* wallet  */ `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="FILL" stroke-width="2.5"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 13h.01"/><path d="M2 10h20"/></svg>`,
];

const CHECK_SVG = `<svg class="check-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00C48C" stroke-width="3" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>`;

function buildProcessingCard(count) {
  const n = count || STEPS.length;
  const rows = STEPS.slice(0, n)
    .map((s, i) => {
      const last = i === n - 1;
      return `
      <div class="step-row">
        <div class="step-track">
          <div class="step-node st-idle" id="sn-${i}">${STEP_ICONS[i].replace(/FILL/g, "#9CA3AF")}</div>
          ${!last ? `<div class="step-line" id="sl-${i}"></div>` : ""}
        </div>
        <div class="step-info">
          <div class="step-label st-idle" id="sk-${i}">${esc(s.label)}</div>
          <div class="step-sublabel">${esc(s.sub)}</div>
        </div>
      </div>`;
    })
    .join("");
  return `<div class="proc-card" id="proc-card">
    <div class="proc-title">Agent Processing</div>
    <div class="steps-list">${rows}</div>
  </div>`;
}

function activateStep(i) {
  const node = document.getElementById(`sn-${i}`);
  const label = document.getElementById(`sk-${i}`);
  if (!node || !label) return;
  node.className = "step-node st-active";
  node.innerHTML = `<div class="spin"></div>`;
  label.className = "step-label st-active";
}

function completeStep(i) {
  const node = document.getElementById(`sn-${i}`);
  const label = document.getElementById(`sk-${i}`);
  const line = document.getElementById(`sl-${i}`);
  if (!node || !label) return;
  node.className = "step-node st-done";
  node.innerHTML = CHECK_SVG;
  label.className = "step-label st-done";
  if (line) line.classList.add("done");
}

function startStepAnimation(upTo) {
  clearStepTimers();
  activateStep(0);

  for (let i = 1; i < upTo; i++) {
    stepTimers.push(
      setTimeout(() => {
        completeStep(i - 1);
        activateStep(i);
      }, i * 900),
    );
  }

  stepTimers.push(
    setTimeout(
      () => {
        for (let i = 0; i < upTo; i++) {
          completeStep(i);
        }
      },
      upTo * 900 + 200,
    ),
  );
}

function finishStepAnimation(total) {
  clearStepTimers();
  for (let i = 0; i < total; i++) {
    completeStep(i);
  }
}

function clearStepTimers() {
  stepTimers.forEach((t) => clearTimeout(t));
  stepTimers = [];
}

function setSendDisabled(val) {
  const btn = document.getElementById("send-btn");
  const inp = document.getElementById("prompt-input");
  if (btn) btn.disabled = val;
  if (inp) inp.disabled = val;
}

async function send() {
  const inputEl = document.getElementById("prompt-input");
  if (!inputEl) {
    showErrToast("⚠️ Input field not found. Please refresh the page.");
    return;
  }
  const prompt = inputEl.value.trim();

  if (!prompt || requestInFlight) return;

  requestInFlight = true;
  verificationId = null;
  inputEl.value = "";
  inputEl.style.height = "auto";

  showChat();
  addUserMsg(prompt);

  const procRow = addAIMsg(buildProcessingCard(3));
  startStepAnimation(3);
  setSendDisabled(true);

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 45000);
    const res = await fetch("/api/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        wallet_address: walletAddress,
        conversation_id: conversationId,
      }),
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      throw new Error(`Server error: ${res.statusText}`);
    }

    const data = await res.json();
    lastVerified = data;
    conversationId = data.conversation_id || conversationId;
    if (conversationId) localStorage.setItem("conversationId", conversationId);
    verificationId = data.verification_id || null;

    finishStepAnimation(3);

    setTimeout(() => {
      procRow.remove();
      renderVerification(data);
      setSendDisabled(false);
      requestInFlight = false;
    }, 800);
  } catch (e) {
    clearStepTimers();
    procRow.remove();
    showErrToast("⚠️ Error: " + e.message);
    setSendDisabled(false);
    requestInFlight = false;
  }
}

function renderVerification(data) {
  if (data.decision === "APPROVED") {
    const intent = data.intent || {};
    const protocol = esc(data.protocol || intent.protocol || "—");
    const action = esc(intent.action || "—");

    let token = "—";
    const tokenIn = intent.token_in ? esc(intent.token_in) : null;
    const tokenOut = intent.token_out ? esc(intent.token_out) : null;
    if (tokenIn && tokenOut) {
      token = `${tokenIn} → ${tokenOut}`;
    } else if (tokenIn) {
      token = tokenIn;
    }

    const amount = esc(String(intent.amount || "—"));
    const executionParameters = data.execution_parameters || {};
    const slippageBps = executionParameters.slippage_bps;
    const slippageDetail = Number.isInteger(slippageBps)
      ? `<div class="detail-item"><label>Maximum slippage</label><span>${esc((slippageBps / 100).toFixed(2))}% (${executionParameters.slippage_source === "user" ? "your limit" : "configured default"})</span></div>`
      : "";

    addAIMsg(`
      <div class="verif-card">
        <div class="verif-head ok">
          <div class="verif-badge ok">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
          <div>
            <div class="verif-head-title ok">Relationship Verified ✓</div>
            <div class="verif-head-sub ok">${data.executable ? "Ready to execute on Sepolia testnet" : "Verification complete — no transaction submitted"}</div>
          </div>
        </div>
        <div class="verif-body">
          <div class="detail-grid">
            <div class="detail-item"><label>Protocol</label><span>${protocol}</span></div>
            <div class="detail-item"><label>Action</label><span>${action}</span></div>
            <div class="detail-item"><label>Token</label><span>${token}</span></div>
            <div class="detail-item"><label>Amount</label><span>${amount}</span></div>
            ${slippageDetail}
          </div>
          <div class="graph-badge">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#065F46" stroke-width="2">
              <circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/>
              <path d="M7 11.5l10-5M7 12.5l10 5"/>
            </svg>
            Verified relationship found in the protocol knowledge graph
          </div>
          ${data.executable && data.verification_id ? `<button class="exec-cta" onclick="executeTransaction()">
            Execute Transaction
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>` : `<div class="info-msg">${esc(data.execution_note || "Graph verification is complete. Transaction execution is not enabled for this operation.")}</div>`}
        </div>
      </div>`);
  } else if (["REJECTED", "UNSUPPORTED", "INSUFFICIENT_EVIDENCE", "BLOCKED"].includes(data.decision)) {
    addAIMsg(`
      <div class="verif-card">
        <div class="verif-head bad">
          <div class="verif-badge bad">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </div>
          <div>
            <div class="verif-head-title bad">${esc(data.decision.replaceAll("_", " "))}</div>
            <div class="verif-head-sub bad">No execution capability was issued</div>
          </div>
        </div>
        <div class="verif-body">
          <div class="reject-msg">
            ${esc(data.reason || data.message || "The request could not be verified.")}
          </div>
        </div>
      </div>`);
  } else if (data.decision === "NEEDS_CLARIFICATION") {
    addAIMsg(`<div class="reject-msg">${esc(data.message || "Please provide more information.")}</div>`);
  } else {
    showErrToast(data.message || "Unexpected response from the server.");
  }
}

async function executeTransaction() {
  if (!verificationId) {
    showErrToast("Verify the operation again before execution.");
    return;
  }
  if (!walletAddress) {
    showErrToast("Please connect a Sepolia wallet before execution.");
    return;
  }

  document.querySelectorAll(".exec-cta").forEach((b) => {
    b.disabled = true;
  });

  const execRow = addAIMsg(`
    <div class="proc-card">
      <div class="proc-title">Executing Transaction</div>
      <div class="exec-loading">
        <div class="spin" style="width:18px;height:18px;border-width:2.5px;"></div>
        <span class="exec-loading-label">Submitting to bundler network…</span>
      </div>
    </div>`);

  try {
    const res = await fetch("/api/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        verification_id: verificationId,
        wallet_address: walletAddress,
      }),
    });
    const data = await res.json();

    setTimeout(() => {
      execRow.remove();
      renderExecution(data);
    }, 700);
  } catch (e) {
    execRow.remove();
    showErrToast("Execution error: " + e.message);
  }
}

function renderExecution(data) {
  if (data.decision === "EXECUTED" && data.execution) {
    const ex = data.execution;
    const intent =
      lastVerified && lastVerified.intent ? lastVerified.intent : {};
    const proto = esc((lastVerified && lastVerified.protocol) || "—");
    const action = esc(intent.action || "—");
    const tokenIn = ex.token_in || intent.token_in || "—";
    const tokenOut = ex.token_out || intent.token_out;
    const token = esc(tokenOut ? `${tokenIn} → ${tokenOut}` : tokenIn);
    const amount = esc(String(intent.amount || "—"));
    const quotedOutput = ex.quoted_amount_out
      ? esc(`${ex.quoted_amount_out} ${ex.token_out || ""}`)
      : null;
    const minimumOutput = ex.minimum_amount_out
      ? esc(`${ex.minimum_amount_out} ${ex.token_out || ""}`)
      : null;
    const hash = esc(ex.tx_hash || "—");
    const wallet = esc(ex.smart_wallet || "—");
    const explorerUrl = ex.explorer ? esc(ex.explorer) : null;

    addAIMsg(`
      <div class="success-card">
        <div class="success-head">
          <div class="success-orb">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          </div>
          <div>
            <div class="success-head-title">Transaction Successful ✓</div>
            <div class="success-head-sub">Confirmed on Sepolia testnet</div>
          </div>
        </div>
        <div class="success-body">
          <div class="success-grid">
            <div class="success-item full">
              <label>Transaction Hash</label>
              <div class="hash-pill">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                  <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
                </svg>${hash}
              </div>
            </div>
            <div class="success-item"><label>Protocol</label><span>${proto}</span></div>
            <div class="success-item"><label>Action</label><span>${action}</span></div>
            <div class="success-item"><label>Token</label><span>${token}</span></div>
            <div class="success-item"><label>Amount</label><span>${amount}</span></div>
            ${quotedOutput ? `<div class="success-item"><label>Quoted output</label><span>${quotedOutput}</span></div>` : ""}
            ${minimumOutput ? `<div class="success-item"><label>Minimum output</label><span>${minimumOutput}</span></div>` : ""}
            <div class="success-item full">
              <label>Smart Wallet</label>
              <span style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;">${wallet}</span>
            </div>
            <div class="success-item">
              <label>Network</label>
              <span>
                <span class="net-chip">
                  <svg width="7" height="7" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4" fill="#00C48C"/></svg>
                  Sepolia
                </span>
              </span>
            </div>
          </div>
          ${
            explorerUrl
              ? `
          <a href="${explorerUrl}" target="_blank" rel="noopener noreferrer" class="view-btn">
            View on Explorer
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>`
              : ""
          }
        </div>
      </div>`);
  } else {
    const reason =
      (data.execution && data.execution.reason) ||
      data.reason ||
      "Transaction execution failed.";
    addAIMsg(`
      <div class="verif-card">
        <div class="verif-head bad">
          <div class="verif-badge bad">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </div>
          <div>
            <div class="verif-head-title bad">Execution Failed</div>
            <div class="verif-head-sub bad">Transaction could not be completed</div>
          </div>
        </div>
        <div class="verif-body">
          <div class="reject-msg">${esc(reason)}</div>
        </div>
      </div>`);
  }
}

async function newOperation() {
  if (conversationId) {
    fetch("/api/conversation/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    }).catch(() => {});
  }
  conversationId = null;
  verificationId = null;
  lastVerified = null;
  localStorage.removeItem("conversationId");
  clearChatHistory();
  const welcome = document.getElementById("welcome-screen");
  const chat = document.getElementById("chat-container");
  if (welcome) welcome.style.display = "flex";
  if (chat) chat.style.display = "none";
}

window.connectWallet = connectWallet;
window.handleInputKey = handleInputKey;
window.autoResize = autoResize;
window.quick = quick;
window.send = send;
window.executeTransaction = executeTransaction;
window.newOperation = newOperation;
