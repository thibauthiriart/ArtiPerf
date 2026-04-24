// Devis Vocal — formulaire : chaque champ a son micro, appel à /dicter-champ.
(() => {
  // ---------- éléments globaux ----------
  const form = document.getElementById("devis-form");
  const champClient = document.getElementById("champ-client");
  const champCategorie = document.getElementById("champ-categorie");
  const clientDbContent = document.getElementById("client-db-content");
  const fournituresList = document.getElementById("fournitures-list");
  const btnAddFourniture = document.getElementById("btn-add-fourniture");
  const debugBlock = document.getElementById("debug");
  const debugJson = document.getElementById("debug-json");

  // ---------- état client (pour gérer ambigu/nouveau) ----------
  let clientState = {
    // "libre" = saisie clavier uniquement, pas de fiche DB
    // "trouve" = fiche validée, client est l'objet DB
    // "ambigu" = en attente de choix
    // "nouveau" = formulaire de création affiché
    mode: "libre",
    client: null,       // fiche DB sélectionnée
    candidats: [],      // si ambigu
    nomEntendu: "",     // dernier nom dicté (utile pour création)
  };

  // ================================================================
  // Helpers DOM
  // ================================================================

  const text = (tag, cls, str) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (str !== undefined) el.textContent = str;
    return el;
  };

  const setMicState = (btn, state) => {
    btn.classList.remove("idle", "recording", "processing");
    btn.classList.add(state);
    btn.disabled = state === "processing";
  };

  const setMicStatus = (champ, msg, kind = "") => {
    const el = document.querySelector(`.mic-status[data-status="${champ}"]`);
    if (!el) return;
    el.className = "mic-status" + (kind ? " " + kind : "");
    el.textContent = msg || "";
  };

  // ================================================================
  // Enregistrement micro (factorisé par champ)
  // ================================================================

  const recorders = {}; // { champ: {mediaRecorder, chunks, stream} }

  const startRecording = async (btn, champ) => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicStatus(champ, "Navigateur sans support micro.", "err");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setMicStatus(champ, "Accès micro refusé : " + err.message, "err");
      return;
    }

    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const mediaRecorder = new MediaRecorder(stream, { mimeType: mime });
    const chunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };
    mediaRecorder.onstop = () => handleStop(btn, champ, chunks, stream);
    mediaRecorder.start();

    recorders[champ] = { mediaRecorder, stream };
    setMicState(btn, "recording");
    setMicStatus(champ, "Enregistrement…");
  };

  const stopRecording = (btn, champ) => {
    const r = recorders[champ];
    if (!r) return;
    r.mediaRecorder.stop();
    r.stream.getTracks().forEach((t) => t.stop());
    delete recorders[champ];
    setMicState(btn, "processing");
    setMicStatus(champ, "Transcription et analyse…");
  };

  const handleStop = async (btn, champ, chunks, _stream) => {
    const blob = new Blob(chunks, { type: "audio/webm" });
    try {
      const fd = new FormData();
      fd.append("champ", champ);
      fd.append("audio", blob, "dictee.webm");

      const resp = await fetch("/dicter-champ", { method: "POST", body: fd });
      const data = await resp.json();

      if (!resp.ok) {
        setMicStatus(champ, "Erreur : " + (data.detail || resp.statusText), "err");
        setMicState(btn, "idle");
        return;
      }

      applyExtraction(champ, data);
      setMicStatus(champ, `Transcrit en ${data.duree_transcription_s}s`, "ok");
    } catch (err) {
      setMicStatus(champ, "Erreur réseau : " + err.message, "err");
    } finally {
      setMicState(btn, "idle");
    }
  };

  // ================================================================
  // Appliquer le résultat d'extraction au formulaire
  // ================================================================

  const applyExtraction = (champ, data) => {
    const d = data.donnees || {};
    if (champ === "client") {
      champClient.value = d.client || "";
      renderClientDb(d.client_db, d.client || "");
    } else if (champ === "categorie") {
      champCategorie.value = d.categorie || "";
    } else if (champ === "fourniture") {
      addFournitureRow({
        description: d.description || "",
        marque: d.marque || "",
        quantite: d.quantite ?? "",
      });
      removeEmptyPlaceholder();
    }
  };

  // ================================================================
  // Fournitures : liste éditable
  // ================================================================

  const removeEmptyPlaceholder = () => {
    const empty = fournituresList.querySelector(".fournitures-empty");
    if (empty) empty.remove();
  };

  const showEmptyPlaceholderIfNeeded = () => {
    if (!fournituresList.querySelector(".fourniture-row")) {
      fournituresList.replaceChildren(
        text("p", "fournitures-empty",
          "Aucune fourniture — dictez-en une ou cliquez sur +"),
      );
    }
  };

  const addFournitureRow = (f = { description: "", marque: "", quantite: "" }) => {
    removeEmptyPlaceholder();

    const row = text("div", "fourniture-row");

    const mkInput = (name, value, placeholder, extraCls = "") => {
      const input = document.createElement("input");
      input.type = name === "quantite" ? "number" : "text";
      input.className = "form-input fourniture-input " + extraCls;
      input.name = name;
      input.value = value ?? "";
      input.placeholder = placeholder;
      if (name === "quantite") input.min = "0";
      return input;
    };

    const descInput = mkInput("description", f.description, "Description", "f-desc");
    const marqueInput = mkInput("marque", f.marque, "Marque", "f-marque");
    const qteInput = mkInput("quantite", f.quantite, "Qté", "f-qte");

    const rmBtn = text("button", "btn-remove", "×");
    rmBtn.type = "button";
    rmBtn.setAttribute("aria-label", "Supprimer cette fourniture");
    rmBtn.addEventListener("click", () => {
      row.remove();
      showEmptyPlaceholderIfNeeded();
    });

    row.append(descInput, marqueInput, qteInput, rmBtn);
    fournituresList.appendChild(row);
    // focus sur la description pour édition rapide si ligne vide
    if (!f.description) descInput.focus();
  };

  btnAddFourniture.addEventListener("click", () => addFournitureRow());

  // ================================================================
  // Rendu de la fiche client DB
  // ================================================================

  const ficheClientHTML = (c) => {
    const card = text("div", "client-card");
    card.append(
      text("div", "client-name", `${c.civilite || ""} ${c.prenom || ""} ${c.nom || ""}`.trim()),
      text("div", "client-line", c.adresse || ""),
      text("div", "client-line", [c.code_postal, c.ville].filter(Boolean).join(" ")),
      text("div", "client-line client-contact", `📞 ${c.telephone || ""}`),
    );
    if (c.email) {
      card.append(text("div", "client-line client-contact", `✉️ ${c.email}`));
    }
    return card;
  };

  const renderConfirmed = (client) => {
    clientState = { mode: "trouve", client, candidats: [], nomEntendu: "" };
    const nomComplet = [client.civilite, client.prenom, client.nom]
      .filter(Boolean).join(" ");
    champClient.value = nomComplet;

    clientDbContent.replaceChildren(
      text("div", "client-status ok", "Client identifié"),
      ficheClientHTML(client),
    );
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
    clientState = { mode: "nouveau", client: null, candidats: [], nomEntendu };
    clientDbContent.replaceChildren();
    clientDbContent.append(
      text("div", "client-status warn",
        "Nouveau client — veuillez renseigner ses informations"),
    );

    const parsed = parseHeardName(nomEntendu);
    const subForm = document.createElement("form");
    subForm.className = "new-client-form";

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

    subForm.append(
      row("Civilité", "civilite", {
        select: true, options: ["", "Madame", "Monsieur"], value: parsed.civilite,
      }),
      row("Prénom", "prenom", { value: parsed.prenom }),
      row("Nom", "nom", { value: parsed.nom, required: true }),
      row("Adresse", "adresse"),
      row("Code postal", "code_postal"),
      row("Ville", "ville"),
      row("Téléphone", "telephone", { type: "tel" }),
      row("Email", "email", { type: "email" }),
    );

    const submit = text("button", "form-submit", "Enregistrer ce client");
    submit.type = "submit";
    subForm.appendChild(submit);
    const errorBox = text("div", "form-error hidden", "");
    subForm.appendChild(errorBox);

    subForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorBox.classList.add("hidden");
      const fd = new FormData(subForm);
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
        const resp = await fetch("/clients", {
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
      } catch (err) {
        errorBox.textContent = "Erreur réseau : " + err.message;
        errorBox.classList.remove("hidden");
      } finally {
        submit.disabled = false;
        submit.textContent = "Enregistrer ce client";
      }
    });

    clientDbContent.appendChild(subForm);
  };

  const renderCandidates = (candidats, nomEntendu) => {
    clientState = { mode: "ambigu", client: null, candidats, nomEntendu };
    clientDbContent.replaceChildren(
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
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(); }
      });
      clientDbContent.appendChild(card);
    }
    const notInDb = text("button", "link-btn", "Ce client n'est pas dans la base");
    notInDb.type = "button";
    notInDb.addEventListener("click", () => renderNewClientForm(nomEntendu));
    clientDbContent.appendChild(notInDb);
  };

  const renderClientDb = (clientDb, nomEntendu) => {
    clientDbContent.replaceChildren();

    if (!clientDb || clientDb.status === "inconnu") {
      const base = nomEntendu || clientDb?.nom_cherche || "";
      if (!base) {
        clientState = { mode: "libre", client: null, candidats: [], nomEntendu: "" };
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
      renderCandidates(clientDb.candidats, nomEntendu);
    }
  };

  // Si l'utilisateur réédite le champ client au clavier, on efface la fiche :
  // le nom saisi ne correspond plus à la fiche confirmée.
  champClient.addEventListener("input", () => {
    if (clientState.mode === "trouve" || clientState.mode === "ambigu") {
      clientDbContent.replaceChildren();
      clientState = { mode: "libre", client: null, candidats: [], nomEntendu: "" };
    }
  });

  // ================================================================
  // Wiring des micros
  // ================================================================

  document.querySelectorAll(".mic-btn[data-target]").forEach((btn) => {
    const champ = btn.getAttribute("data-target");
    btn.addEventListener("click", () => {
      if (btn.classList.contains("idle")) startRecording(btn, champ);
      else if (btn.classList.contains("recording")) stopRecording(btn, champ);
    });
  });

  // ================================================================
  // Soumission : assemble un JSON de devis
  // ================================================================

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const fournitures = [];
    fournituresList.querySelectorAll(".fourniture-row").forEach((row) => {
      const desc = row.querySelector(".f-desc").value.trim();
      const marque = row.querySelector(".f-marque").value.trim();
      const qteRaw = row.querySelector(".f-qte").value.trim();
      if (!desc && !marque && !qteRaw) return;
      fournitures.push({
        description: desc || null,
        marque: marque || null,
        quantite: qteRaw ? Number(qteRaw) : null,
      });
    });

    const devis = {
      client: champClient.value.trim() || null,
      client_db: clientState.mode === "trouve" ? clientState.client : null,
      categorie: champCategorie.value.trim() || null,
      fournitures,
    };

    debugJson.textContent = JSON.stringify(devis, null, 2);
    debugBlock.classList.remove("hidden");
    debugBlock.open = true;
  });
})();
