let walletAddress = null;

async function connectWallet() {
  if (!window.ethereum) {
    alert("MetaMask not found. Install it from metamask.io");
    return;
  }
  try {
    const provider = new ethers.providers.Web3Provider(window.ethereum);
    await provider.send("eth_requestAccounts", []);
    const signer = provider.getSigner();
    walletAddress = await signer.getAddress();
    const short = walletAddress.slice(0,6)+"..."+walletAddress.slice(-4);
    document.getElementById("wallet-btn").textContent = short;
    document.getElementById("wallet-btn").classList.add("bg-green-50","border-green-300");
    document.getElementById("wallet-info").classList.remove("hidden");
    document.getElementById("wallet-info").textContent =
      "Connected: " + walletAddress;
  } catch(e) {
    alert("Wallet connection failed: " + e.message);
  }
}

async function send() {
  const input = document.getElementById("input");
  const prompt = input.value.trim();
  if (!prompt) return;
  input.value = "";
  addMessage("user", prompt);
  addMessage("system", "Verifying...", "pending");
  try {
    const res = await fetch("/api/verify", {
      method:  "POST",
      headers: {"Content-Type":"application/json"},
      body:    JSON.stringify({ prompt, wallet_address: walletAddress })
    });
    const data = await res.json();
    console.log("Response:", data);
    removePending();
    renderResult(data);
  } catch(e) {
    removePending();
    addMessage("system", "Error: " + e.message, "error");
  }
}

function renderResult(data) {
  if (data.decision === "APPROVED") {
    addMessage("system",
      `APPROVED\n` +
      `Address : ${data.verified_address}\n` +
      `Protocol: ${data.protocol}\n` +
      `Action  : ${data.intent?.action}\n` +
      `Latency : ${data.latency_ms}ms`,
      "approved");
  } else if (data.decision === "BLOCKED") {
    addMessage("system",
      `BLOCKED\n${data.reason}\nLatency: ${data.latency_ms}ms`,
      "blocked");
  } else {
    addMessage("system", data.message || "Unknown error", "error");
  }
}

function addMessage(role, text, type) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");
  div.className = "rounded-lg px-4 py-3 text-sm whitespace-pre-wrap " +
    (role === "user"
      ? "bg-gray-900 text-white ml-8"
      : type === "approved"
        ? "bg-green-50 border border-green-200 text-green-800 font-mono"
        : type === "blocked"
          ? "bg-red-50 border border-red-200 text-red-800 font-mono"
          : type === "pending"
            ? "bg-gray-100 text-gray-500 italic"
            : "bg-gray-100 text-gray-700");
  if (type === "pending") div.id = "pending-msg";
  div.textContent = text;
  chat.appendChild(div);
  div.scrollIntoView({behavior:"smooth"});
}

function removePending() {
  const p = document.getElementById("pending-msg");
  if (p) p.remove();
}

function quick(text) {
  document.getElementById("input").value = text;
  send();
}