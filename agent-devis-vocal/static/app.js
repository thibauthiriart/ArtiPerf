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
  const devisLignes = document.getElementById("devis-lignes");
  const devisTotauxBlock = document.getElementById("devis-totaux");
  const devisTotalHt = document.getElementById("devis-total-ht");
  const devisTotalWarn = document.getElementById("devis-total-warn");

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

  const clientsList = document.getElementById("clients-list");

  // ---------- usage / coût ----------
  const sessionUsage = {
    requests: 0,
    inputTokens: 0,
    outputTokens: 0,
    audioSeconds: 0,
    costUsd: 0,
  };

  const fmtUsd = (v) => "$" + (v || 0).toFixed(5);
  const fmtTokens = (n) => `${n.toLocaleString("fr-FR")} tok`;

  const updateLastUsage = (usage) => {
    const last = document.getElementById("usage-last");
    last.classList.remove("hidden");
    document.getElementById("usage-last-cost").textContent = fmtUsd(usage.total_cost_usd);

    const w = usage.whisper || {};
    document.getElementById("usage-w-model").textContent = w.model ? `(${w.model})` : "";
    document.getElementById("usage-w-line").textContent =
      `${(w.audio_seconds || 0).toFixed(1)}s audio · ${fmtUsd(w.cost_usd)}`;

    const r = usage.llm_routeur || {};
    document.getElementById("usage-r-model").textContent = r.model ? `(${r.model})` : "";
    document.getElementById("usage-r-line").textContent =
      `${r.input_tokens || 0} in + ${r.output_tokens || 0} out · ${fmtUsd(r.cost_usd)}`;

    const o = usage.llm_outil || {};
    document.getElementById("usage-o-name").textContent = o.nom || "";
    document.getElementById("usage-o-model").textContent = o.model ? `(${o.model})` : "";
    document.getElementById("usage-o-line").textContent =
      `${o.input_tokens || 0} in + ${o.output_tokens || 0} out · ${fmtUsd(o.cost_usd)}`;
  };

  const updateSessionUsage = (usage) => {
    const w = usage.whisper || {};
    const r = usage.llm_routeur || {};
    const o = usage.llm_outil || {};

    sessionUsage.requests += 1;
    sessionUsage.inputTokens += (r.input_tokens || 0) + (o.input_tokens || 0);
    sessionUsage.outputTokens += (r.output_tokens || 0) + (o.output_tokens || 0);
    sessionUsage.audioSeconds += w.audio_seconds || 0;
    sessionUsage.costUsd += usage.total_cost_usd || 0;

    document.getElementById("usage-session-tokens").textContent =
      fmtTokens(sessionUsage.inputTokens + sessionUsage.outputTokens) +
      ` (${sessionUsage.inputTokens} in / ${sessionUsage.outputTokens} out)`;
    document.getElementById("usage-session-audio").textContent =
      sessionUsage.audioSeconds.toFixed(1) + " s audio";
    document.getElementById("usage-session-cost").textContent = fmtUsd(sessionUsage.costUsd);
    document.getElementById("usage-session-count").textContent = sessionUsage.requests;
  };

  // ---------- liste des clients (sidebar) ----------
  const renderClientsList = (clients) => {
    clientsList.replaceChildren();
    if (!clients || clients.length === 0) {
      const li = document.createElement("li");
      li.className = "clients-empty";
      li.textContent = "Aucun client en base.";
      clientsList.appendChild(li);
      return;
    }
    for (const c of clients) {
      const li = document.createElement("li");
      li.className = "client-item";
      const name = document.createElement("span");
      name.className = "client-item-name";
      name.textContent = [c.civilite, c.prenom, c.nom].filter(Boolean).join(" ");
      li.appendChild(name);
      if (c.ville) {
        const city = document.createElement("span");
        city.className = "client-item-city";
        city.textContent = [c.code_postal, c.ville].filter(Boolean).join(" ");
        li.appendChild(city);
      }
      clientsList.appendChild(li);
    }
  };

  const refreshClientsList = async () => {
    try {
      const resp = await fetch("clients");
      if (!resp.ok) throw new Error(resp.statusText);
      const data = await resp.json();
      renderClientsList(data);
    } catch (err) {
      clientsList.replaceChildren();
      const li = document.createElement("li");
      li.className = "clients-empty";
      li.textContent = "Impossible de charger la liste.";
      clientsList.appendChild(li);
    }
  };

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
  let currentNomEntendu = "";

  const renderConfirmed = (client) => {
    // 1. Met à jour le bloc "Devis extrait" : nom corrigé + adresse + tél
    const nomComplet = [client.civilite, client.prenom, client.nom]
      .filter(Boolean)
      .join(" ");
    devisClient.replaceChildren(formatValue(nomComplet));
    devisAddressValue.textContent = [
      client.adresse,
      [client.code_postal, client.ville].filter(Boolean).join(" "),
    ].filter(Boolean).join(", ");
    devisAddressField.classList.remove("hidden");
    devisPhoneValue.textContent = client.telephone || "";
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
      btn.addEventListener("click", () => renderCandidates(currentAmbigu, currentNomEntendu));
      clientDbContent.append(btn);
    }
  };

  const renderCandidates = (candidats, nomEntendu) => {
    clearClientFields();
    clientDbContent.replaceChildren();
    clientDbContent.append(
      text("div", "client-status warn",
        `${candidats.length} client(s) correspondent — cliquez sur le bon`),
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

    const notInDb = text("button", "link-btn", "Ce client n'est pas dans la base");
    notInDb.type = "button";
    notInDb.addEventListener("click", () => {
      clientDbContent.replaceChildren();
      renderNewClientForm(nomEntendu);
    });
    clientDbContent.appendChild(notInDb);
  };

  const capitalize = (s) =>
    s ? s.charAt(0).toUpperCase() + s.slice(1) : "";

  const CIVILITE_MAP = {
    "monsieur": "Monsieur", "mr": "Monsieur", "m": "Monsieur",
    "madame": "Madame", "mme": "Madame",
    "mademoiselle": "Madame", "mlle": "Madame",
  };

  const parseHeardName = (heard) => {
    if (!heard) return { civilite: "", prenom: "", nom: "" };
    const tokens = heard.trim().split(/\s+/).filter(Boolean);
    const norm = (w) => w.toLowerCase().replace(/\.$/, "");

    let civilite = "";
    let i = 0;
    if (tokens.length && CIVILITE_MAP[norm(tokens[0])]) {
      civilite = CIVILITE_MAP[norm(tokens[0])];
      i = 1;
    }
    const rest = tokens.slice(i);
    if (rest.length === 0) return { civilite, prenom: "", nom: "" };
    if (rest.length === 1) return { civilite, prenom: "", nom: capitalize(rest[0]) };
    return {
      civilite,
      prenom: rest.slice(0, -1).map(capitalize).join(" "),
      nom: capitalize(rest[rest.length - 1]),
    };
  };

  const renderNewClientForm = (nomEntendu) => {
    clientDbContent.append(
      text("div", "client-status warn",
        "Nouveau client — veuillez renseigner ses informations personnelles"),
    );

    const parsed = parseHeardName(nomEntendu);

    const form = document.createElement("form");
    form.className = "new-client-form";

    const row = (label, name, opts = {}) => {
      const wrap = document.createElement("label");
      wrap.className = "form-row";
      wrap.append(text("span", "form-label", label));
      const input = document.createElement(opts.select ? "select" : "input");
      input.name = name;
      input.className = "form-input";
      if (opts.select) {
        for (const v of opts.options) {
          const o = document.createElement("option");
          o.value = v;
          o.textContent = v || "—";
          if (opts.value && v === opts.value) o.selected = true;
          input.appendChild(o);
        }
      } else {
        input.type = opts.type || "text";
      }
      if (opts.value && !opts.select) input.value = opts.value;
      if (opts.required) input.required = true;
      wrap.appendChild(input);
      return wrap;
    };

    form.append(
      row("Civilité", "civilite", {
        select: true,
        options: ["", "Madame", "Monsieur"],
        value: parsed.civilite,
      }),
      row("Prénom", "prenom", { value: parsed.prenom }),
      row("Nom", "nom", { value: parsed.nom, required: true }),
      row("Adresse", "adresse"),
      row("Code postal", "code_postal"),
      row("Ville", "ville"),
      row("Téléphone", "telephone", { type: "tel" }),
      row("Email", "email", { type: "email" }),
    );

    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "form-submit";
    submit.textContent = "Enregistrer ce client";
    form.appendChild(submit);

    const errorBox = text("div", "form-error hidden", "");
    form.appendChild(errorBox);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.classList.add("hidden");

      const fd = new FormData(form);
      const payload = {
        civilite: (fd.get("civilite") || "").trim(),
        prenom: (fd.get("prenom") || "").trim(),
        nom: (fd.get("nom") || "").trim(),
        adresse: (fd.get("adresse") || "").trim(),
        code_postal: (fd.get("code_postal") || "").trim(),
        ville: (fd.get("ville") || "").trim(),
        telephone: (fd.get("telephone") || "").trim(),
        email: (fd.get("email") || "").trim(),
      };

      submit.disabled = true;
      submit.textContent = "Enregistrement…";
      try {
        const resp = await fetch("clients", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json();
        if (!resp.ok) {
          errorBox.textContent = data.detail || `Erreur ${resp.status}`;
          errorBox.classList.remove("hidden");
          return;
        }
        renderConfirmed(data);
        refreshClientsList();
      } catch (err) {
        errorBox.textContent = "Erreur réseau : " + err.message;
        errorBox.classList.remove("hidden");
      } finally {
        submit.disabled = false;
        submit.textContent = "Enregistrer ce client";
      }
    });

    clientDbContent.appendChild(form);
  };

  const renderClientDb = (clientDb, nomEntendu) => {
    clearClientFields();
    clientDbContent.replaceChildren();
    currentAmbigu = null;
    currentNomEntendu = nomEntendu || "";

    if (!clientDb || clientDb.status === "inconnu") {
      const base = nomEntendu || clientDb?.nom_cherche || "";
      if (!base) {
        clientDbContent.append(
          text("div", "client-unknown",
            "Aucun client n'a été détecté dans la dictée."),
        );
        return;
      }
      renderNewClientForm(base);
      return;
    }

    if (clientDb.status === "trouve") {
      renderConfirmed(clientDb.client);
      return;
    }

    if (clientDb.status === "ambigu") {
      currentAmbigu = clientDb.candidats;
      renderCandidates(clientDb.candidats, nomEntendu);
    }
  };

  const TYPE_LABEL = {
    fourniture: "Fourniture",
    pose: "Pose",
    frais_annexe: "Frais",
  };
  const SOUS_TYPE_LABEL = {
    transport: "Transport",
    deplacement: "Déplacement",
    location_materiel: "Location matériel",
    evacuation_dechets: "Évacuation déchets",
    autre: "Autre",
  };
  const UNITE_LABEL = {
    piece: "pièce",
    m2: "m²",
    ml: "ml",
    heure: "h",
    forfait: "forfait",
  };

  const fmtEur = (v) =>
    v == null ? null : v.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

  const fmtQte = (q, unite) => {
    if (q == null) return "—";
    const u = UNITE_LABEL[unite] || unite || "";
    if (unite === "forfait") return u;
    const n = Number.isInteger(q) ? q : q.toLocaleString("fr-FR");
    return `${n} ${u}`.trim();
  };

  const renderDevis = (devis) => {
    devisClient.replaceChildren(formatValue(devis.client));
    devisDomaine.replaceChildren(formatValue(devis.domaine));

    devisLignes.replaceChildren();
    const lignes = devis.lignes || [];

    if (lignes.length === 0) {
      const empty = document.createElement("p");
      empty.className = "missing";
      empty.textContent = "Aucune ligne détectée";
      devisLignes.appendChild(empty);
      devisTotauxBlock.classList.add("hidden");
      return;
    }

    for (const l of lignes) {
      const card = document.createElement("div");
      card.className = `ligne-card ligne-type-${l.type}`;
      if (l.prix_a_completer) card.classList.add("ligne-incomplete");

      // Header : badge type + description + (marque)
      const head = document.createElement("div");
      head.className = "ligne-head";

      const badge = document.createElement("span");
      badge.className = `ligne-badge badge-${l.type}`;
      badge.textContent = l.sous_type
        ? SOUS_TYPE_LABEL[l.sous_type] || TYPE_LABEL[l.type]
        : TYPE_LABEL[l.type] || l.type;
      head.appendChild(badge);

      const desc = document.createElement("span");
      desc.className = "ligne-desc";
      desc.textContent = l.description || "—";
      head.appendChild(desc);

      if (l.marque) {
        const marque = document.createElement("span");
        marque.className = "ligne-marque";
        marque.textContent = l.marque;
        head.appendChild(marque);
      }

      card.appendChild(head);

      // Détail : qté × prix = total
      const detail = document.createElement("div");
      detail.className = "ligne-detail";

      const qte = document.createElement("span");
      qte.className = "ligne-qte";
      qte.textContent = fmtQte(l.quantite, l.unite);

      const sep = document.createElement("span");
      sep.className = "ligne-sep";
      sep.textContent = "×";

      const prix = document.createElement("span");
      prix.className = "ligne-prix";
      if (l.prix_unitaire_ht == null) {
        prix.textContent = "prix à compléter";
        prix.classList.add("ligne-warn");
      } else {
        prix.textContent = fmtEur(l.prix_unitaire_ht) + " HT";
      }

      const total = document.createElement("span");
      total.className = "ligne-total";
      total.textContent = l.total_ligne_ht == null ? "—" : fmtEur(l.total_ligne_ht) + " HT";

      detail.append(qte, sep, prix, document.createTextNode("="), total);
      card.appendChild(detail);

      devisLignes.appendChild(card);
    }

    // Totaux
    devisTotauxBlock.classList.remove("hidden");
    devisTotalHt.textContent = fmtEur(devis.total_devis_ht || 0) + " HT";
    if (devis.total_complet === false) {
      devisTotalWarn.classList.remove("hidden");
      devisTotalWarn.textContent = "⚠️ Total partiel — certaines lignes ont un prix à compléter.";
    } else {
      devisTotalWarn.classList.add("hidden");
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

      const resp = await fetch("dicter-devis", { method: "POST", body: fd });
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

        renderClientDb(resultat.devis.client_db, resultat.devis.client);
        clientDbPanel.classList.remove("hidden");
      } else {
        messageText.textContent = resultat.message || "Aucun devis détecté.";
        messagePanel.classList.remove("hidden");
      }

      // Usage / coût
      if (data.usage) {
        updateLastUsage(data.usage);
        updateSessionUsage(data.usage);
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
  refreshClientsList();
})();
