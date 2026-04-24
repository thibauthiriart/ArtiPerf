// Devis Vocal : enregistrement micro → POST /dicter-devis → affichage structuré.
(() => {
  const btn = document.getElementById("btn");
  const timer = document.getElementById("timer");
  const status = document.getElementById("status");

  const transcriptPanel = document.getElementById("transcript");
  const transcriptText = document.getElementById("transcript-text");

  const devisPanel = document.getElementById("devis");
  const devisClient = document.getElementById("devis-client");
  const devisDomaine = document.getElementById("devis-domaine");
  const devisFournitures = document.getElementById("devis-fournitures");

  const clientDbPanel = document.getElementById("client-db");
  const clientDbContent = document.getElementById("client-db-content");

  const devisAddressField = document.getElementById("devis-address-field");
  const devisAddressValue = document.getElementById("devis-address");
  const devisPhoneField = document.getElementById("devis-phone-field");
  const devisPhoneValue = document.getElementById("devis-phone");

  const messagePanel = document.getElementById("message");
  const messageText = document.getElementById("message-text");

  const debugBlock = document.getElementById("debug");
  const debugJson = document.getElementById("debug-json");

  let mediaRecorder = null;
  let chunks = [];
  let stream = null;
  let tickInterval = null;
  let startTs = 0;

  // ---------- états du bouton ----------
  const setState = (state) => {
    btn.classList.remove("idle", "recording", "processing");
    btn.classList.add(state);
    btn.disabled = state === "processing";
  };

  const setStatus = (msg, kind = "") => {
    status.className = "status" + (kind ? " " + kind : "");
    status.textContent = msg;
  };

  const hidePanels = () => {
    [transcriptPanel, devisPanel, clientDbPanel, messagePanel, debugBlock].forEach((p) =>
      p.classList.add("hidden"),
    );
    devisAddressField.classList.add("hidden");
    devisPhoneField.classList.add("hidden");
  };

  // ---------- rendu du devis ----------
  const formatValue = (v) => {
    if (v === null || v === undefined || v === "") {
      const span = document.createElement("span");
      span.className = "missing";
      span.textContent = "non précisé";
      return span;
    }
    return document.createTextNode(String(v));
  };

  // ---------- rendu de la fiche client DB ----------
  const text = (tag, cls, str) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    el.textContent = str;
    return el;
  };

  const ficheClientHTML = (c) => {
    const card = document.createElement("div");
    card.className = "client-card";
    card.append(
      text("div", "client-name", `${c.civilite} ${c.prenom} ${c.nom}`),
      text("div", "client-line", c.adresse),
      text("div", "client-line", `${c.code_postal} ${c.ville}`),
      text("div", "client-line client-contact", `📞 ${c.telephone}`),
    );
    if (c.email) {
      card.append(text("div", "client-line client-contact", `✉️ ${c.email}`));
    }
    return card;
  };

  const clearClientFields = () => {
    devisAddressField.classList.add("hidden");
    devisAddressValue.textContent = "";
    devisPhoneField.classList.add("hidden");
    devisPhoneValue.textContent = "";
  };

  // État stocké en mémoire pour gérer la resélection
  let currentAmbigu = null;

  const renderConfirmed = (client) => {
    // 1. Met à jour le bloc "Devis extrait" avec l'adresse et le tél du client
    devisAddressValue.textContent = `${client.adresse}, ${client.code_postal} ${client.ville}`;
    devisAddressField.classList.remove("hidden");
    devisPhoneValue.textContent = client.telephone;
    devisPhoneField.classList.remove("hidden");

    // 2. Remplace la fiche client par l'état "identifié"
    clientDbContent.replaceChildren();
    clientDbContent.append(
      text("div", "client-status ok", "Client identifié"),
      ficheClientHTML(client),
    );

    // 3. Si c'était ambigu, propose de revenir au choix
    if (currentAmbigu && currentAmbigu.length > 1) {
      const btn = text("button", "link-btn", "↺ Choisir un autre client");
      btn.type = "button";
      btn.addEventListener("click", () => renderCandidates(currentAmbigu));
      clientDbContent.append(btn);
    }
  };

  const renderCandidates = (candidats) => {
    clearClientFields();
    clientDbContent.replaceChildren();
    clientDbContent.append(
      text("div", "client-status warn",
        `${candidats.length} clients correspondent — cliquez sur le bon`),
    );

    for (const c of candidats) {
      const card = ficheClientHTML(c);
      card.classList.add("client-card-choice");
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      const choose = () => renderConfirmed(c);
      card.addEventListener("click", choose);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          choose();
        }
      });
      clientDbContent.appendChild(card);
    }
  };

  const renderClientDb = (clientDb) => {
    clearClientFields();
    clientDbContent.replaceChildren();
    currentAmbigu = null;

    if (!clientDb || clientDb.status === "inconnu") {
      const nom = clientDb?.nom_cherche;
      const msg = nom
        ? `Aucun client trouvé pour « ${nom} » dans la base.`
        : "Aucun client n'a été détecté dans la dictée.";
      clientDbContent.append(text("div", "client-unknown", msg));
      return;
    }

    if (clientDb.status === "trouve") {
      renderConfirmed(clientDb.client);
      return;
    }

    if (clientDb.status === "ambigu") {
      currentAmbigu = clientDb.candidats;
      renderCandidates(clientDb.candidats);
    }
  };

  const renderDevis = (devis) => {
    devisClient.replaceChildren(formatValue(devis.client));
    devisDomaine.replaceChildren(formatValue(devis.domaine));

    devisFournitures.replaceChildren();
    const fournitures = devis.fournitures || [];

    if (fournitures.length === 0) {
      const empty = document.createElement("p");
      empty.className = "missing";
      empty.textContent = "Aucune fourniture détectée";
      devisFournitures.appendChild(empty);
      return;
    }

    for (const f of fournitures) {
      const card = document.createElement("div");
      card.className = "fourniture-card";

      const desc = document.createElement("div");
      desc.className = "fourniture-desc";
      desc.textContent = f.description || "—";

      const marque = document.createElement("div");
      marque.className = "fourniture-line";
      marque.append("Marque : ", formatValue(f.marque));

      const qte = document.createElement("div");
      qte.className = "fourniture-line";
      qte.append("Quantité : ", formatValue(f.quantite));

      card.append(desc, marque, qte);
      devisFournitures.appendChild(card);
    }
  };

  // ---------- enregistrement ----------
  const startRecording = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("Le navigateur ne supporte pas l'enregistrement audio.", "err");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setStatus("Accès micro refusé : " + err.message, "err");
      return;
    }

    hidePanels();
    chunks = [];

    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    mediaRecorder = new MediaRecorder(stream, { mimeType: mime });

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };
    mediaRecorder.onstop = handleStop;

    mediaRecorder.start();
    setState("recording");
    setStatus("Enregistrement en cours…");
    startTs = Date.now();
    tick();
    tickInterval = setInterval(tick, 100);
  };

  const stopRecording = () => {
    if (!mediaRecorder) return;
    mediaRecorder.stop();
    stream?.getTracks().forEach((t) => t.stop());
    clearInterval(tickInterval);
    setState("processing");
    setStatus("Transcription et analyse…");
  };

  const tick = () => {
    const s = ((Date.now() - startTs) / 1000).toFixed(1);
    timer.textContent = `${s}s`;
  };

  const handleStop = async () => {
    const blob = new Blob(chunks, { type: "audio/webm" });
    try {
      const fd = new FormData();
      fd.append("audio", blob, "dictee.webm");

      const resp = await fetch("/dicter-devis", { method: "POST", body: fd });
      const data = await resp.json();

      if (!resp.ok) {
        setStatus("Erreur : " + (data.detail || resp.statusText), "err");
        setState("idle");
        return;
      }

      // Transcription
      transcriptText.textContent = data.texte_transcrit;
      transcriptPanel.classList.remove("hidden");

      // Résultat
      const resultat = data.resultat || {};
      if (resultat.type === "devis" && resultat.devis) {
        renderDevis(resultat.devis);
        devisPanel.classList.remove("hidden");

        renderClientDb(resultat.devis.client_db);
        clientDbPanel.classList.remove("hidden");
      } else {
        messageText.textContent = resultat.message || "Aucun devis détecté.";
        messagePanel.classList.remove("hidden");
      }

      // Debug
      debugJson.textContent = JSON.stringify(data, null, 2);
      debugBlock.classList.remove("hidden");

      setStatus("Terminé.", "ok");
      timer.textContent = "";
    } catch (err) {
      setStatus("Erreur réseau : " + err.message, "err");
    } finally {
      setState("idle");
    }
  };

  btn.addEventListener("click", () => {
    if (btn.classList.contains("idle")) startRecording();
    else if (btn.classList.contains("recording")) stopRecording();
  });

  setState("idle");
})();
