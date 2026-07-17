const state = {
  cards: [], filtered: [], visible: 48, selected: null, tab: "attributes", returnToLineup: false,
  returnToDraft: false, returnToDraftChoices: false,
  randomLineup: [], draftSelections: {}, draftTarget: null, draftOptions: [], draftDiamondSelection: null, draftMode: "default",
  customSelections: [], customFiltered: [], imageManifest: {}, jerseyNumberOverrides: { cards: {}, playerTeamYears: {}, players: {} }, injectionState: null, injectionKind: null, injectionRosterPath: "", injectionTeam: "", injectionTeamMode: "nba", unlockedInjectionTeams: {}, pendingUnlockTeam: "", loadedRosterVerification: null, manualLoadedRosterConfirm: false,
  savedLineups: [], savedLineupKind: "", myteamExclusiveNames: new Set()
};
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const elements = {
  search: $("#search"), tier: $("#tierFilter"), team: $("#teamFilter"), position: $("#positionFilter"),
  theme: $("#themeFilter"), overall: $("#overallFilter"), sort: $("#sortFilter"), grid: $("#cardGrid"),
  resultTitle: $("#resultTitle"), loadMore: $("#loadMore"), activeFilters: $("#activeFilters"),
  modal: $("#detailModal"), tabContent: $("#tabContent"), filters: $("#filters"),
  lineupModal: $("#lineupModal"), lineupGrid: $("#lineupGrid"),
  draftModal: $("#draftModal"), draftGrid: $("#draftGrid"),
  draftChoiceModal: $("#draftChoiceModal"), draftChoiceGrid: $("#draftChoiceGrid"),
  saveToast: $("#saveToast"), diamondRound: $("#diamondRound"),
  customModal: $("#customModal"), customSelectedGrid: $("#customSelectedGrid"), customPickerGrid: $("#customPickerGrid"),
  customCount: $("#customCount"), customSearch: $("#customSearch"), customTier: $("#customTierFilter"), customPosition: $("#customPositionFilter"), customTeam: $("#customTeamFilter"),
  injectionModal: $("#injectionModal"), rosterSelect: $("#rosterSelect"), rosterHint: $("#rosterHint"),
  injectionTeamGrid: $("#injectionTeamGrid"), injectionTeamHeading: $("#injectionTeamHeading"), toggleHistoricTeams: $("#toggleHistoricTeams"), injectionSummary: $("#injectionSummary"), confirmInjection: $("#confirmInjection"),
  verifyLoadedRoster: $("#verifyLoadedRoster"), resetRosterTracking: $("#resetRosterTracking"), confirmLoadedRoster: $("#confirmLoadedRoster"), loadedRosterStatus: $("#loadedRosterStatus"),
  manualRosterDir: $("#manualRosterDir"), saveRosterDir: $("#saveRosterDir"), manualRosterDirStatus: $("#manualRosterDirStatus"),
  unlockTeamModal: $("#unlockTeamModal"), confirmTeamUnlock: $("#confirmTeamUnlock"),
  savedLineupModal: $("#savedLineupModal"), savedLineupList: $("#savedLineupList"), savedLineupHint: $("#savedLineupHint"),
  viewLineupFromChoices: $("#viewLineupFromChoices")
};
const tierOrder = ["Diamond", "Amethyst", "Gold", "Silver", "Bronze"];
const tierClass = tier => `tier-${(tier || "unknown").toLowerCase().replace(/[^a-z]+/g, "-")}`;
const galleryTierRank = { Diamond: 0, Amethyst: 1, Gold: 2, Silver: 3, Bronze: 4 };
const finalDiamondCardId = 10072; // 95 OVR Luis Scola closes the Diamond section.
const hotZoneTemplateUrl = "assets/hot-zone-template.png";
const hotZoneNeutral = [100, 100, 99];
const hotZoneColors = { 0: [14, 88, 157], 1: hotZoneNeutral, 2: [182, 19, 19] };
const hotZoneSeedPoints = {
  under_basket: [104, 265], close_left: [112, 367], close_center: [193, 265], close_right: [115, 165],
  mid_left: [132, 448], mid_left_center: [296, 365], mid_center: [298, 265], mid_right_center: [298, 165], mid_right: [140, 90],
  three_left: [190, 510], three_left_center: [397, 447], three_center: [397, 265], three_right_center: [397, 135], three_right: [190, 20]
};
const pretty = text => text.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase()).replace(" Iq", " IQ");
const imageKey = card => `${card.id}-${(card.slug || "").toLowerCase().replace(/[^a-z0-9-]+/g, "-")}`;
const artUrl = card => {
  const entry = state.imageManifest[imageKey(card)];
  if (typeof entry === "string") return entry;
  if (entry?.path) return entry.path;
  return "assets/photo-missing.svg";
};
function cardImageHtml(card, className = "", alt = "", fast = true) {
  const label = alt || `${card.name} MyTEAM card`;
  return `<img${className ? ` class="${className}"` : ""} loading="eager" decoding="async" src="${artUrl(card)}" alt="${escapeHtml(label)}" onerror="retryCardArt(this)">`;
}
window.refreshFastArt = image => {
  if (!image.src.includes("fast=1") || image.dataset.fullRefreshQueued) return;
  image.dataset.fullRefreshQueued = "1";
  window.setTimeout(() => {
    const full = image.src.replace(/([?&])fast=1&?/, "$1").replace(/[?&]$/, "");
    image.src = `${full}${full.includes("?") ? "&" : "?"}refresh=${Date.now()}`;
  }, 2200);
};
window.retryCardArt = image => {
  const attempts = Number(image.dataset.retryAttempts || 0);
  if (attempts >= 3) return;
  image.dataset.retryAttempts = String(attempts + 1);
  const base = image.src.split("&retry=")[0].split("?retry=")[0];
  const separator = base.includes("?") ? "&" : "?";
  window.setTimeout(() => { image.src = `${base}${separator}retry=${Date.now()}-${attempts}`; }, 450 + attempts * 800);
};
const imageObserver = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    const image = entry.target;
    image.src = image.dataset.src;
    imageObserver.unobserve(image);
  });
}, { rootMargin: "260px 0px" }) : null;

function addOptions(select, values, preferred = []) {
  const sorted = [...values].filter(Boolean).sort((a,b) => {
    const ai = preferred.indexOf(a), bi = preferred.indexOf(b);
    if (ai >= 0 || bi >= 0) return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi);
    return a.localeCompare(b);
  });
  select.insertAdjacentHTML("beforeend", sorted.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join(""));
}
function escapeHtml(value = "") { const span = document.createElement("span"); span.textContent = String(value); return span.innerHTML; }
function debounce(fn, wait = 130) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); }; }

function applyFilters() {
  const query = elements.search.value.trim().toLowerCase();
  const tier = elements.tier.value, team = elements.team.value, position = elements.position.value;
  const theme = elements.theme.value, minimum = Number(elements.overall.value || 0);
  state.filtered = state.cards.filter(card => {
    const haystack = `${card.name} ${card.collection} ${card.theme} ${card.franchise} ${card.year || ""}`.toLowerCase();
    return (!query || haystack.includes(query)) && (!tier || card.tier === tier) && (!team || card.franchise === team)
      && (!position || card.position === position || card.secondaryPosition === position)
      && (!theme || card.theme === theme) && card.overall >= minimum;
  });
  const sorter = elements.sort.value;
  state.filtered.sort((a,b) => {
    if (sorter === "name") return a.name.localeCompare(b.name) || b.overall - a.overall;
    if (sorter === "year-desc") return (b.year || 0) - (a.year || 0) || b.overall - a.overall;
    if (sorter === "year-asc") return (a.year || 9999) - (b.year || 9999) || b.overall - a.overall;
    if (sorter === "id-desc") return b.id - a.id;
    const tierDifference = (galleryTierRank[a.tier] ?? 9) - (galleryTierRank[b.tier] ?? 9);
    if (tierDifference) return tierDifference;
    const aIsFinalDiamond = a.tier === "Diamond" && a.id === finalDiamondCardId;
    const bIsFinalDiamond = b.tier === "Diamond" && b.id === finalDiamondCardId;
    if (aIsFinalDiamond !== bIsFinalDiamond) return aIsFinalDiamond ? 1 : -1;
    return b.overall - a.overall || a.name.localeCompare(b.name) || b.id - a.id;
  });
  state.visible = 48;
  renderCards(); renderActiveFilters();
}

function renderCards() {
  const shown = state.filtered.slice(0, state.visible);
  elements.grid.replaceChildren();
  if (!shown.length) {
    elements.grid.innerHTML = `<div class="empty-state"><h3>No cards found</h3><p>Try clearing one of the filters.</p></div>`;
  } else {
    const fragment = document.createDocumentFragment();
    shown.forEach(card => {
      const node = $("#cardTemplate").content.firstElementChild.cloneNode(true);
      node.classList.add(tierClass(card.tier)); node.dataset.cardKey = `${card.id}/${card.slug}`;
      const image = $("img", node); image.loading = "eager"; image.decoding = "async"; image.dataset.src = artUrl(card, true); image.src = image.dataset.src; image.alt = `${card.year || "NBA 2K16"} ${card.name} ${card.tier} card`;
      image.onerror = () => window.retryCardArt(image);
      $("h3", node).textContent = card.name;
      $(".card-subtitle", node).textContent = `${card.year || "Current"} · ${card.franchise}`;
      $(".card-overall", node).textContent = card.overall;
      fragment.append(node);
    });
    elements.grid.append(fragment);
  }
  elements.resultTitle.textContent = `${state.filtered.length.toLocaleString()} card${state.filtered.length === 1 ? "" : "s"}`;
  elements.loadMore.hidden = state.visible >= state.filtered.length;
}

function renderActiveFilters() {
  const filters = [
    ["tier", elements.tier, "Tier"], ["team", elements.team, "Team"], ["position", elements.position, "Position"],
    ["theme", elements.theme, "Theme"], ["overall", elements.overall, "Overall"]
  ].filter(([,element]) => element.value && !(element === elements.overall && element.value === "0"));
  elements.activeFilters.innerHTML = filters.map(([key,element,label]) => `<button class="filter-pill" data-clear="${key}">${label}: ${escapeHtml(element.options[element.selectedIndex].text)} ×</button>`).join("");
}

function clearFilter(key) {
  const map = { tier: elements.tier, team: elements.team, position: elements.position, theme: elements.theme, overall: elements.overall };
  if (map[key]) map[key].value = key === "overall" ? "0" : "";
  applyFilters();
}
function clearAllFilters() {
  elements.search.value = ""; elements.tier.value = ""; elements.team.value = ""; elements.position.value = "";
  elements.theme.value = ""; elements.overall.value = "0"; elements.sort.value = "overall"; applyFilters();
}

function openCard(card, preferredArtSrc = "") {
  state.selected = card; state.tab = "attributes";
  elements.modal.className = `modal open ${tierClass(card.tier)}`; elements.modal.setAttribute("aria-hidden", "false");
  $(".detail-panel").className = `detail-panel ${tierClass(card.tier)}`;
  $("#detailArt").dataset.retryAttempts = "0"; $("#detailArt").src = preferredArtSrc || artUrl(card, true); $("#detailArt").alt = `${card.name} MyTEAM card`;
  $("#detailName").textContent = card.name; $("#detailOverall").textContent = card.overall;
  $("#detailCollection").textContent = card.collection || card.theme || "NBA 2K16 MyTEAM";
  $("#detailChips").innerHTML = [card.tier, card.year || "Current", [card.position,card.secondaryPosition].filter(Boolean).join(" / "), card.franchise]
    .filter(Boolean).map(value => `<span class="detail-chip">${escapeHtml(value)}</span>`).join("");
  $$(".tab").forEach(tab => tab.classList.toggle("active", tab.dataset.tab === "attributes"));
  renderTab(); document.body.classList.add("modal-open");
}
function openCardFromDraft(card, returnToChoices = false, preferredArtSrc = "") {
  state.returnToDraft = !returnToChoices;
  state.returnToDraftChoices = returnToChoices;
  elements.draftChoiceModal.classList.remove("open");
  elements.draftChoiceModal.setAttribute("aria-hidden", "true");
  elements.draftModal.classList.remove("open");
  elements.draftModal.setAttribute("aria-hidden", "true");
  openCard(card, preferredArtSrc);
}
function closeModal() {
  elements.modal.classList.remove("open");
  elements.modal.setAttribute("aria-hidden", "true");
  state.selected = null;
  if (state.returnToLineup) {
    state.returnToLineup = false;
    renderRandomLineupGrid();
    elements.lineupModal.classList.add("open");
    elements.lineupModal.setAttribute("aria-hidden", "false");
  } else if (state.returnToDraftChoices) {
    state.returnToDraftChoices = false;
    renderCurrentDraftChoices();
    elements.draftModal.classList.add("open");
    elements.draftModal.setAttribute("aria-hidden", "false");
    elements.draftChoiceModal.classList.add("open");
    elements.draftChoiceModal.setAttribute("aria-hidden", "false");
  } else if (state.returnToDraft) {
    state.returnToDraft = false;
    elements.draftModal.classList.add("open");
    elements.draftModal.setAttribute("aria-hidden", "false");
    setTimeout(() => focusNextDraftTarget(), 60);
  } else {
    document.body.classList.remove("modal-open");
  }
}

const lineupPositions = ["PG", "SG", "SF", "PF", "C"];
const lineupTierWeights = { bronze: .85, silver: .85, gold: 1, amethyst: 1.10, diamond: 1.10 };
function weightedRandomChoice(items) {
  const weights = items.map(card => lineupTierWeights[(card.tier || "").toLowerCase()] ?? 1);
  let roll = Math.random() * weights.reduce((sum, weight) => sum + weight, 0);
  for (let index = 0; index < items.length; index++) {
    roll -= weights[index];
    if (roll <= 0) return items[index];
  }
  return items[items.length - 1];
}
function createRandomLineup() {
  state.returnToLineup = false;
  const usedPlayers = new Set();
  let bronzeUsed = false;
  const guaranteedPremiumIndex = Math.floor(Math.random() * lineupPositions.length);
  const lineup = lineupPositions.map((position,index) => {
    let eligible = state.cards.filter(card => card.position === position && !usedPlayers.has(card.name));
    if (index === guaranteedPremiumIndex) eligible = eligible.filter(card => card.tier === "Diamond" || card.tier === "Amethyst");
    else if (bronzeUsed) eligible = eligible.filter(card => card.tier !== "Bronze");
    const card = weightedRandomChoice(eligible);
    if (card) { usedPlayers.add(card.name); if (card.tier === "Bronze") bronzeUsed = true; }
    return { position, card };
  });
  state.randomLineup = lineup;
  elements.lineupGrid.innerHTML = state.randomLineup.map(({position,card}) => card ? `<button class="lineup-card ${tierClass(card.tier)}" data-card-key="${card.id}/${escapeHtml(card.slug)}" aria-label="View ${escapeHtml(card.name)} at ${position}">
    <span class="lineup-position">${position}</span><span class="lineup-art" data-initials="${escapeHtml(card.name.split(/\s+/).slice(0,2).map(part => part[0]).join(""))}">${cardImageHtml(card)}</span>
    <span class="lineup-card-copy"><span><h3>${escapeHtml(card.name)}</h3><p>${card.year || "Current"} · ${escapeHtml(card.franchise)}</p></span><span class="lineup-overall">${card.overall}</span></span>
    <span class="lineup-tier">${escapeHtml(card.tier)}</span></button>` : "").join("");
  elements.lineupModal.classList.add("open");
  elements.lineupModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}
function renderRandomLineupGrid() {
  elements.lineupGrid.innerHTML = state.randomLineup.map(({position,card}) => card ? `<button class="lineup-card ${tierClass(card.tier)}" data-card-key="${card.id}/${escapeHtml(card.slug)}" aria-label="View ${escapeHtml(card.name)} at ${position}">
    <span class="lineup-position">${position}</span><span class="lineup-art" data-initials="${escapeHtml(card.name.split(/\s+/).slice(0,2).map(part => part[0]).join(""))}">${cardImageHtml(card)}</span>
    <span class="lineup-card-copy"><span><h3>${escapeHtml(card.name)}</h3><p>${card.year || "Current"} Â· ${escapeHtml(card.franchise)}</p></span><span class="lineup-overall">${card.overall}</span></span>
    <span class="lineup-tier">${escapeHtml(card.tier)}</span></button>` : "").join("");
  preloadArt(state.randomLineup.map(entry => entry.card).filter(Boolean), true, 700);
}
function closeLineup() {
  state.returnToLineup = false;
  elements.lineupModal.classList.remove("open");
  elements.lineupModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

const draftRoles = ["starter", "backup"];
const benchRoles = ["bench1", "bench2"];
const draftOddsByMode = {
  baller: {
    starter: [["Diamond",.20],["Amethyst",.40],["Gold",.20],["Silver",.099],["Bronze",.001]],
    backup: [["Diamond",.05],["Amethyst",.20],["Gold",.60],["Silver",.10],["Bronze",.05]],
    bench: [["Diamond",.01],["Amethyst",.09],["Gold",.40],["Silver",.40],["Bronze",.10]]
  },
  default: {
    starter: [["Diamond",.05],["Amethyst",.20],["Gold",.40],["Silver",.30],["Bronze",.05]],
    backup: [["Diamond",.0025],["Amethyst",.0375],["Gold",.26],["Silver",.50],["Bronze",.20]],
    bench: [["Diamond",.0001],["Amethyst",.001],["Gold",.01],["Silver",.40],["Bronze",.5889]]
  },
  budget: {
    starter: [["Diamond",.002],["Amethyst",.098],["Gold",.40],["Silver",.40],["Bronze",.10]],
    backup: [["Diamond",.001],["Amethyst",.019],["Gold",.15],["Silver",.60],["Bronze",.23]],
    bench: [["Diamond",.00001],["Amethyst",.0001],["Gold",.001],["Silver",.15],["Bronze",.84889]]
  }
};
const draftModeLabels = { baller: "Baller Draft", default: "Default Draft", budget: "Budget Draft" };
const draftOdds = () => draftOddsByMode[state.draftMode] || draftOddsByMode.default;
const slotKey = (role,position) => `${role}|${position}`;
const benchSlotKey = number => `bench|${number}`;
const randomItem = items => items[Math.floor(Math.random() * items.length)];
function draftChoiceItem(items) {
  if (!items.length) return null;
  return randomItem(items);
}
const positionDraftKeys = () => lineupPositions.flatMap(position => draftRoles.map(role => slotKey(role,position)));
const benchDraftKeys = () => benchRoles.map((_, index) => benchSlotKey(index + 1));
const allDraftKeys = () => [...positionDraftKeys(), ...benchDraftKeys()];
const positionDraftComplete = () => positionDraftKeys().every(key => state.draftSelections[key]);
const draftFilledCount = () => allDraftKeys().map(key => state.draftSelections[key]).filter(Boolean).length;
const draftComplete = () => draftFilledCount() === allDraftKeys().length;
function nextDraftKey() {
  return allDraftKeys().find(key => !state.draftSelections[key]) || "";
}
function focusNextDraftTarget() {
  if (!elements.draftModal.classList.contains("open") || elements.draftChoiceModal.classList.contains("open")) return;
  const key = nextDraftKey();
  const target = key ? elements.draftGrid.querySelector(`[data-draft-slot="${CSS.escape(key)}"]`) : $("#startDiamondRound") || $("#returnDiamondChoices");
  if (target) target.focus?.({ preventScroll: true });
}
function rollDraftTier(role) {
  const odds = draftOdds();
  const table = role === "bench" ? odds.bench : odds[role];
  let roll = Math.random();
  for (const [tier,chance] of table) { roll -= chance; if (roll < 0) return tier; }
  return table[table.length - 1][0];
}
function formatDraftChance(chance) {
  const percent = chance * 100;
  if (percent < .01) return `${percent.toFixed(3).replace(/0+$/,"").replace(/\.$/,"")}%`;
  if (percent < 1) return `${percent.toFixed(2).replace(/0+$/,"").replace(/\.$/,"")}%`;
  return `${percent.toFixed(1).replace(/\.0$/,"")}%`;
}
function draftModeTooltip(mode) {
  const odds = draftOddsByMode[mode] || draftOddsByMode.default;
  return [`${draftModeLabels[mode] || "Draft"} odds`,
    `Starter: ${odds.starter.map(([tier,chance]) => `${tier} ${formatDraftChance(chance)}`).join(" · ")}`,
    `Backup: ${odds.backup.map(([tier,chance]) => `${tier} ${formatDraftChance(chance)}`).join(" · ")}`,
    `Deep Bench: ${odds.bench.map(([tier,chance]) => `${tier} ${formatDraftChance(chance)}`).join(" · ")}`
  ].join("\n");
}
function renderDraftModeButtons() {
  $$("[data-draft-mode]").forEach(button => {
    const mode = button.dataset.draftMode || "default";
    button.classList.toggle("active", mode === state.draftMode);
    button.setAttribute("aria-pressed", mode === state.draftMode ? "true" : "false");
    button.dataset.tooltip = draftModeTooltip(mode);
  });
}
function setDraftMode(mode) {
  state.draftMode = draftOddsByMode[mode] ? mode : "default";
  renderDraftModeButtons();
  renderDiamondRound();
}
function draftBonusRoundConfig() {
  if (state.draftMode === "budget") {
    return {
      title: "Amethyst Round",
      pendingTitle: "Amethyst round unlocks after the draft",
      pendingCopy: "Fill all 12 slots, then choose 1 of 5 mostly-amethyst bonus cards as your 13th roster player.",
      unlockedTitle: "Amethyst round unlocked",
      unlockedCopy: "Pick 1 of 5 bonus cards as your 13th player. Each option has a 1% Diamond / 99% Amethyst roll.",
      returnTitle: "Return to amethyst picks",
      returnCopy: "Your five Amethyst Round choices are still waiting.",
      modalSubtitle: "Choose one bonus card as your 13th roster player. Each choice rolls 1% Diamond and 99% Amethyst.",
      tiers: [["Diamond", .01], ["Amethyst", .99]]
    };
  }
  return {
    title: "Diamond Round",
    pendingTitle: "Diamond round unlocks after the draft",
    pendingCopy: "Fill all 12 slots, then choose 1 of 5 guaranteed diamonds as your 13th roster player.",
    unlockedTitle: "Diamond round unlocked",
    unlockedCopy: "Pick 1 of 5 guaranteed diamonds as your 13th player. Positions can repeat; players cannot.",
    returnTitle: "Return to diamond picks",
    returnCopy: "Your five guaranteed diamond choices are still waiting.",
    modalSubtitle: "Choose one guaranteed diamond as your 13th roster player. Your drafted 12 stay locked.",
    tiers: [["Diamond", 1]]
  };
}
function cardInitials(card) { return card.name.split(/\s+/).slice(0,2).map(part => part[0]).join(""); }
function renderDiamondRound() {
  const completed = draftComplete();
  const bonus = draftBonusRoundConfig();
  elements.diamondRound.classList.toggle("amethyst-round", state.draftMode === "budget");
  if (state.draftDiamondSelection) {
    const card = state.draftDiamondSelection;
    elements.diamondRound.innerHTML = `<div class="diamond-round-card diamond-round-complete diamond-roster-card ${tierClass(card.tier)}"><span class="draft-slot-art" data-initials="${escapeHtml(cardInitials(card))}">${cardImageHtml(card)}</span><strong>13th pick: ${escapeHtml(card.name)}</strong><span>${card.year || "Current"} · ${escapeHtml(card.franchise)} · ${escapeHtml(card.position)} · ${card.overall} OVR</span><button class="diamond-view-card" data-view-card="${card.id}/${escapeHtml(card.slug)}">View card</button></div>`;
    return;
  }
  if (!completed) {
    elements.diamondRound.innerHTML = `<div class="diamond-round-card"><strong>${bonus.pendingTitle}</strong><span>${bonus.pendingCopy}</span><em>${draftFilledCount()}/12 drafted</em></div>`;
    return;
  }
  if (state.draftTarget === "diamond-round" && state.draftOptions.length) {
    elements.diamondRound.innerHTML = `<button id="returnDiamondChoices" class="diamond-round-button"><strong>${bonus.returnTitle}</strong><span>${bonus.returnCopy}</span></button>`;
    return;
  }
  elements.diamondRound.innerHTML = `<button id="startDiamondRound" class="diamond-round-button"><strong>${bonus.unlockedTitle}</strong><span>${bonus.unlockedCopy}</span></button>`;
}
function draftSlotMarkup(key, role, position, locked = false) {
  const card = state.draftSelections[key];
  if (!card) {
    const lockText = locked ? "Complete the 10 starter/backup picks first" : "Choose from 5 cards";
    return `<button class="draft-slot draft-slot-empty${locked ? " draft-slot-disabled" : ""}" ${locked ? "disabled" : `data-draft-slot="${key}"`} aria-label="Draft ${role} ${position}"><span>+</span><strong>${pretty(role)} ${position}</strong><small>${lockText}</small></button>`;
  }
  return `<button class="draft-slot draft-slot-locked ${tierClass(card.tier)}" data-view-card="${card.id}/${escapeHtml(card.slug)}" aria-label="View locked ${role} ${position}: ${escapeHtml(card.name)}"><span class="draft-role">${pretty(role)} <em>${position}</em></span><span class="draft-slot-art" data-initials="${escapeHtml(cardInitials(card))}">${cardImageHtml(card)}</span><span class="draft-slot-copy"><strong>${escapeHtml(card.name)}</strong><b>${card.overall}</b></span><span class="draft-slot-meta">${card.year || "Current"} · ${escapeHtml(card.tier)}</span></button>`;
}
function renderDraftGrid() {
  renderDraftModeButtons();
  renderDiamondRound();
  const positionColumns = lineupPositions.map(position => `<section class="draft-position-column"><h3 class="draft-position-heading">${position}</h3>${draftRoles.map(role => draftSlotMarkup(slotKey(role,position), role, position)).join("")}</section>`);
  const benchLocked = !positionDraftComplete();
  const benchColumns = benchRoles.map((role, index) => `<section class="draft-position-column draft-bench-column draft-bench-${index + 1}"><h3 class="draft-position-heading">DEEP BENCH</h3>${draftSlotMarkup(benchSlotKey(index + 1), "bench", "FLEX", benchLocked)}</section>`);
  elements.draftGrid.innerHTML = [...positionColumns, ...benchColumns].join("");
}
function openDraft() {
  setDraftMode("default");
  renderDraftGrid();
  elements.draftModal.classList.add("open");
  elements.draftModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  setTimeout(() => focusNextDraftTarget(), 80);
}
function closeDraftChoices() {
  elements.draftChoiceModal.classList.remove("open");
  elements.draftChoiceModal.setAttribute("aria-hidden", "true");
  elements.viewLineupFromChoices.hidden = true;
  state.draftTarget = null;
  state.draftOptions = [];
}
function closeDraft() {
  closeDraftChoices();
  elements.draftModal.classList.remove("open");
  elements.draftModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function customCardMarkup(card,index) {
  return `<button class="custom-selected-item ${tierClass(card.tier)}" data-remove-custom="${index}" aria-label="Remove ${escapeHtml(card.name)}"><span class="draft-slot-art" data-initials="${escapeHtml(cardInitials(card))}">${cardImageHtml(card)}</span><strong>${escapeHtml(card.name)}</strong><small>${card.year || "Current"} · ${escapeHtml(card.tier)} · ${card.overall} OVR</small></button>`;
}
function renderCustomSelected() {
  elements.customCount.textContent = `${state.customSelections.length}/13 selected`;
  elements.customSelectedGrid.innerHTML = Array.from({length: 13}, (_,index) => {
    const card = state.customSelections[index];
    if (card) return customCardMarkup(card,index);
    return `<div class="custom-empty-slot"><span>${index + 1}</span><strong>Empty slot</strong></div>`;
  }).join("");
}
function applyCustomFilters() {
  const query = elements.customSearch.value.trim().toLowerCase();
  const tier = elements.customTier.value;
  const position = elements.customPosition.value;
  const team = elements.customTeam.value;
  state.customFiltered = state.cards.filter(card => {
    const haystack = `${card.name} ${card.collection} ${card.theme} ${card.franchise} ${card.year || ""}`.toLowerCase();
    return (!query || haystack.includes(query)) && (!tier || card.tier === tier) && (!position || card.position === position || card.secondaryPosition === position) && (!team || card.franchise === team);
  }).sort((a,b) => b.overall - a.overall || a.name.localeCompare(b.name)).slice(0, 80);
  elements.customPickerGrid.innerHTML = state.customFiltered.map((card,index) => `<article class="custom-picker-item ${tierClass(card.tier)}"><span class="lineup-art" data-initials="${escapeHtml(cardInitials(card))}">${cardImageHtml(card)}</span><div><strong>${escapeHtml(card.name)}</strong><small>${card.year || "Current"} · ${escapeHtml(card.franchise)} · ${escapeHtml(card.tier)} · ${card.overall} OVR</small></div><button class="choice-draft-button" data-add-custom="${index}" ${state.customSelections.length >= 13 ? "disabled" : ""}>Add card</button></article>`).join("");
  preloadArt(state.customFiltered.slice(0,24), true, 700);
}
function renderCustomBuilder() {
  renderCustomSelected();
  applyCustomFilters();
}
function openCustomTeam() {
  renderCustomBuilder();
  elements.customModal.classList.add("open");
  elements.customModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}
function closeCustomTeam() {
  elements.customModal.classList.remove("open");
  elements.customModal.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}
function draftChoiceMarkup(card,index,label) {
  const positionText = state.draftTarget === "diamond-round" ? ` · ${escapeHtml(card.position)}` : "";
  return `<article class="draft-choice-card ${tierClass(card.tier)}" aria-label="${escapeHtml(card.name)} draft choice"><button class="choice-view-button" data-choice-view="${index}">View badges & attributes</button><span class="lineup-art" data-initials="${escapeHtml(cardInitials(card))}">${cardImageHtml(card,"","",true)}</span><h3>${escapeHtml(card.name)}</h3><p>${card.year || "Current"} · ${escapeHtml(card.franchise)}${positionText}</p><span class="choice-card-footer"><span>${escapeHtml(card.tier)}</span><strong>${card.overall}</strong></span><button class="choice-draft-button" data-choice-index="${index}">${label}</button></article>`;
}
function draftChoiceButtonLabel(card) {
  return state.draftTarget === "diamond-round" ? "Add as 13th pick" : `Draft ${escapeHtml(card.name)}`;
}
function renderCurrentDraftChoices() {
  if (!state.draftOptions.length) return;
  elements.draftChoiceGrid.innerHTML = state.draftOptions.map((card,index) => draftChoiceMarkup(card,index,draftChoiceButtonLabel(card))).join("");
  preloadArt(state.draftOptions, true, 700);
}
function preloadArt(cards, fast = true, timeoutMs = 1400) {
  const jobs = cards.map(card => new Promise(resolve => {
    const image = new Image();
    const timer = setTimeout(resolve, timeoutMs);
    image.onload = image.onerror = () => { clearTimeout(timer); resolve(); };
    image.src = artUrl(card, fast);
  }));
  return Promise.allSettled(jobs);
}
function showDraftChoices(title, subtitle, choices, buttonLabel) {
  $("#choiceTitle").textContent = title;
  $("#choiceSubtitle").textContent = subtitle;
  elements.viewLineupFromChoices.hidden = state.draftTarget !== "diamond-round";
  elements.draftChoiceGrid.innerHTML = `<div class="choice-pack-opening"><div class="pack-card pack-card-one"></div><div class="pack-card pack-card-two"></div><div class="pack-card pack-card-three"></div><strong>Opening MyTEAM pack…</strong><p>Revealing your five choices.</p></div>`;
  elements.draftChoiceModal.classList.add("open");
  elements.draftChoiceModal.setAttribute("aria-hidden", "false");
  preloadArt(choices, false, 450).finally(() => {
    if (state.draftOptions !== choices) return;
    renderCurrentDraftChoices();
  });
}
function openDraftChoices(key) {
  const [role,position] = key.split("|");
  if (role === "bench" && !positionDraftComplete()) return;
  const unavailable = new Set(Object.values(state.draftSelections).map(card => card.name));
  const offered = new Set();
  const choices = [];
  for (let option = 0; option < 5; option++) {
    const tier = rollDraftTier(role);
    const positionOk = card => role === "bench" ? lineupPositions.includes(card.position) : card.position === position;
    let eligible = state.cards.filter(card => positionOk(card) && card.tier === tier && !unavailable.has(card.name) && !offered.has(card.name));
    if (!eligible.length) eligible = state.cards.filter(card => positionOk(card) && !unavailable.has(card.name) && !offered.has(card.name));
    const card = draftChoiceItem(eligible);
    if (card) { choices.push(card); offered.add(card.name); }
  }
  state.draftTarget = key;
  state.draftOptions = choices;
  const title = role === "bench" ? `Choose Your Bench ${position}` : `Choose Your ${pretty(role)} ${position}`;
  const subtitle = role === "bench" ? "Five independently rolled choices using the special final-bench odds." : "Five independently rolled choices — select one card to fill this slot.";
  showDraftChoices(title, subtitle, choices, card => `Draft ${escapeHtml(card.name)}`);
}
function openDiamondRoundChoices() {
  if (!draftComplete() || state.draftDiamondSelection) return;
  const bonus = draftBonusRoundConfig();
  if (state.draftTarget === "diamond-round" && state.draftOptions.length) {
    renderCurrentDraftChoices();
    elements.viewLineupFromChoices.hidden = false;
    elements.draftChoiceModal.classList.add("open");
    elements.draftChoiceModal.setAttribute("aria-hidden", "false");
    return;
  }
  const unavailable = new Set([...Object.values(state.draftSelections), state.draftDiamondSelection].filter(Boolean).map(card => card.name));
  const offered = new Set();
  const choices = [];
  for (let option = 0; option < 5; option++) {
    let roll = Math.random();
    let tier = bonus.tiers[bonus.tiers.length - 1][0];
    for (const [candidateTier, chance] of bonus.tiers) {
      roll -= chance;
      if (roll < 0) { tier = candidateTier; break; }
    }
    let eligible = state.cards.filter(card => card.tier === tier && lineupPositions.includes(card.position) && !unavailable.has(card.name) && !offered.has(card.name));
    if (!eligible.length) {
      const allowedTiers = new Set(bonus.tiers.map(([candidateTier]) => candidateTier));
      eligible = state.cards.filter(card => allowedTiers.has(card.tier) && lineupPositions.includes(card.position) && !unavailable.has(card.name) && !offered.has(card.name));
    }
    const card = draftChoiceItem(eligible);
    if (card) { choices.push(card); offered.add(card.name); }
  }
  state.draftTarget = "diamond-round";
  state.draftOptions = choices;
  showDraftChoices(bonus.title, bonus.modalSubtitle, choices, () => "Add as 13th pick");
}

const exportTierColors = { Diamond:"#a9f4ff", Amethyst:"#b97cff", Gold:"#f2cf61", Silver:"#cbd5df", Bronze:"#c78964" };
function loadedCardImage(card) {
  const marker = `/art/${card.id}/`;
  return [...document.images].find(image => image.src.includes(marker) && image.complete && image.naturalWidth > 0);
}
function fitText(ctx,text,maxWidth,startSize=23) {
  let size = startSize;
  do { ctx.font = `800 ${size}px Arial`; size--; } while (ctx.measureText(text).width > maxWidth && size > 11);
}
function drawExportCard(ctx,entry,x,y,width,height) {
  const { position,role,card } = entry;
  const color = card ? (exportTierColors[card.tier] || "#5ce1e6") : "#405266";
  ctx.fillStyle = "#0e1721"; ctx.fillRect(x,y,width,height);
  ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.strokeRect(x+1,y+1,width-2,height-2);
  ctx.fillStyle = color; ctx.font = "900 17px Arial"; ctx.fillText(position,x+16,y+28);
  ctx.fillStyle = "#91a0b2"; ctx.font = "700 13px Arial"; ctx.textAlign = "right"; ctx.fillText(role.toUpperCase(),x+width-16,y+27); ctx.textAlign = "left";
  const artX=x+14, artY=y+43, artW=width-28, artH=height-128;
  ctx.fillStyle="#081018"; ctx.fillRect(artX,artY,artW,artH);
  if (card) {
    const image = loadedCardImage(card);
    if (image) {
      const scale = Math.min(artW/image.naturalWidth,artH/image.naturalHeight);
      const drawW=image.naturalWidth*scale, drawH=image.naturalHeight*scale;
      ctx.drawImage(image,artX+(artW-drawW)/2,artY+(artH-drawH)/2,drawW,drawH);
    } else {
      ctx.fillStyle=color;ctx.globalAlpha=.55;ctx.font="900 52px Arial";ctx.textAlign="center";ctx.fillText(cardInitials(card),artX+artW/2,artY+artH/2);ctx.textAlign="left";ctx.globalAlpha=1;
    }
    ctx.fillStyle="#f5f7fa"; fitText(ctx,card.name,width-88); ctx.fillText(card.name,x+15,y+height-55);
    ctx.fillStyle=color;ctx.font="900 27px Arial";ctx.textAlign="right";ctx.fillText(String(card.overall),x+width-15,y+height-53);ctx.textAlign="left";
    ctx.fillStyle="#91a0b2";ctx.font="12px Arial";ctx.fillText(`${card.year || "Current"} · ${card.tier}`,x+15,y+height-28);
  } else {
    ctx.fillStyle="#637488";ctx.font="700 19px Arial";ctx.textAlign="center";ctx.fillText("EMPTY SLOT",x+width/2,artY+artH/2);ctx.textAlign="left";
  }
}
function lineupCanvas(kind) {
  const isDraft = kind === "draft";
  const isCustom = kind === "custom";
  const canvas = document.createElement("canvas");
  canvas.width = isDraft || isCustom ? 2200 : 1800; canvas.height = isDraft ? (state.draftDiamondSelection ? 1560 : 1120) : isCustom ? 1220 : 700;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0,0,canvas.width,canvas.height); gradient.addColorStop(0,"#071019");gradient.addColorStop(1,isDraft?"#171022":isCustom?"#0f1d17":"#09151e");ctx.fillStyle=gradient;ctx.fillRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle="#5ce1e6";ctx.font="800 17px Arial";ctx.fillText(isDraft?"NBA 2K16 MYTEAM · 12-PLAYER DRAFT":"NBA 2K16 MYTEAM · RANDOM STARTING FIVE",55,48);
  ctx.fillStyle="#f5f7fa";ctx.font="900 42px Arial";ctx.fillText(isDraft?"My Drafted Team":"My Random Lineup",55,98);
  ctx.fillStyle="#91a0b2";ctx.font="15px Arial";ctx.fillText(new Date().toLocaleString(),55,127);
  const width=isDraft ? 290 : 320,gap=isDraft ? 18 : 22,startX=56;
  if (isDraft) {
    lineupPositions.forEach((position,index) => {
      const x=startX+index*(width+gap);
      drawExportCard(ctx,{position,role:"starter",card:state.draftSelections[slotKey("starter",position)]},x,160,width,430);
      drawExportCard(ctx,{position,role:"backup",card:state.draftSelections[slotKey("backup",position)]},x,620,width,430);
    });
    benchRoles.forEach((role,index) => {
      const x=startX+(lineupPositions.length+index)*(width+gap);
      drawExportCard(ctx,{position:`B${index+1}`,role:"bench",card:state.draftSelections[benchSlotKey(index+1)]},x,160,width,430);
    });
    if (state.draftDiamondSelection) {
      ctx.fillStyle="#5ce1e6";ctx.font="800 17px Arial";ctx.fillText("DIAMOND ROUND BONUS",55,1120);
      drawExportCard(ctx,{position:state.draftDiamondSelection.position || "DIAMOND",role:"13th pick",card:state.draftDiamondSelection},55,1150,width,360);
    }
  } else if (isCustom) {
    state.customSelections.forEach((card,index) => {
      const col = index % 7;
      const row = Math.floor(index / 7);
      const label = index < 5 ? ["PG","SG","SF","PF","C"][index] : index < 12 ? `B${index - 4}` : "13";
      const role = index < 5 ? "starter" : index < 12 ? "bench" : "13th pick";
      drawExportCard(ctx,{position:label,role,card},startX+col*(width+gap),170+row*470,width,430);
    });
  } else {
    state.randomLineup.forEach((entry,index) => drawExportCard(ctx,{...entry,role:"starter"},startX+index*(width+gap),170,width,460));
  }
  return canvas;
}
let toastTimer;
function showSaveToast(message,error=false) {
  clearTimeout(toastTimer); elements.saveToast.textContent=message; elements.saveToast.className=`save-toast show${error?" error":""}`;
  toastTimer=setTimeout(()=>elements.saveToast.className="save-toast",6500);
}
function screenshotRegionFor(kind) {
  const panel = kind === "draft" ? $(".draft-panel") : kind === "custom" ? $(".custom-panel") : $(".lineup-panel");
  if (!panel) return null;
  const rect = panel.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const borderX = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
  const borderY = Math.max(0, window.outerHeight - window.innerHeight - borderX);
  return {
    left: (window.screenX + borderX + Math.max(0, rect.left)) * dpr,
    top: (window.screenY + borderY + Math.max(0, rect.top)) * dpr,
    right: (window.screenX + borderX + Math.min(window.innerWidth, rect.right)) * dpr,
    bottom: (window.screenY + borderY + Math.min(window.innerHeight, rect.bottom)) * dpr,
    dpr
  };
}
async function saveLineup(kind) {
  if (kind === "random" && state.randomLineup.length !== 5) { showSaveToast("Generate a lineup before saving it.",true); return; }
  if (kind === "draft" && (!draftComplete() || !state.draftDiamondSelection)) { showSaveToast("Your lineup is incomplete",true); return; }
  if (kind === "custom" && state.customSelections.length !== 13) { showSaveToast("Your lineup is incomplete",true); return; }
  try {
    const response = await fetch("/api/save-lineup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind,lineup:lineupSaveData(kind),screenshotRegion:screenshotRegionFor(kind),image:lineupCanvas(kind).toDataURL("image/png")})});
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Could not save lineup");
    showSaveToast(`Saved to ${result.path} — the Saved Lineups folder is next to the app.`);
  } catch (error) { showSaveToast(error.message,true); }
}

function cardRef(card) {
  return card ? { id: card.id, slug: card.slug } : null;
}
function findCard(ref) {
  if (!ref) return null;
  return state.cards.find(card => String(card.id) === String(ref.id) && String(card.slug) === String(ref.slug));
}
function lineupSaveData(kind) {
  if (kind === "random") {
    return {
      kind,
      title: "Random Lineup",
      slots: state.randomLineup.map(entry => ({ position: entry.position, card: cardRef(entry.card) }))
    };
  }
  if (kind === "custom") {
    return {
      kind,
      title: "Custom Team",
      cards: state.customSelections.map(cardRef)
    };
  }
  return {
    kind,
    title: "Drafted Team",
    selections: Object.fromEntries(Object.entries(state.draftSelections).map(([key, card]) => [key, cardRef(card)])),
    diamond: cardRef(state.draftDiamondSelection)
  };
}
function closeSavedLineups() {
  elements.savedLineupModal.classList.remove("open");
  elements.savedLineupModal.setAttribute("aria-hidden", "true");
}
function renderSavedLineups() {
  const kind = state.savedLineupKind;
  const records = state.savedLineups.filter(item => item.kind === kind);
  const label = kind === "draft" ? "drafted teams" : kind === "custom" ? "custom teams" : "random lineups";
  $("#savedLineupTitle").textContent = `Load ${kind === "draft" ? "Drafted Team" : kind === "custom" ? "Custom Team" : "Random Lineup"}`;
  elements.savedLineupHint.textContent = records.length ? `Choose one of your saved ${label}.` : `No saved ${label} with reload data were found yet. Save one first, then it will appear here.`;
  elements.savedLineupList.innerHTML = records.length ? records.map((item,index) => {
    const count = item.count || (kind === "random" ? 5 : 13);
    const names = (item.preview || []).slice(0, 5).map(escapeHtml).join(", ");
    return `<button class="saved-lineup-item" data-load-saved="${index}">
      <strong>${escapeHtml(item.title || item.filename || "Saved lineup")}</strong>
      <span>${escapeHtml(item.createdText || "")} · ${count} players</span>
      <small>${names || "Saved lineup data"}</small>
    </button>`;
  }).join("") : `<div class="empty-state"><p>No restorable saved lineups found for this mode yet.</p></div>`;
  if (records.length) {
    elements.savedLineupList.querySelectorAll("[data-load-saved]").forEach((node, index) => {
      const item = records[index];
      const label = item?.title || item?.filename || "saved lineup";
      node.insertAdjacentHTML("afterend", `<button class="saved-lineup-delete" data-delete-saved="${index}" aria-label="Delete ${escapeHtml(label)}">Delete</button>`);
    });
  }
}
async function openSavedLineups(kind) {
  state.savedLineupKind = kind;
  elements.savedLineupList.innerHTML = `<div class="empty-state"><p>Loading saved lineups…</p></div>`;
  elements.savedLineupModal.classList.add("open");
  elements.savedLineupModal.setAttribute("aria-hidden", "false");
  try {
    const response = await fetch("/api/saved-lineups", { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Could not load saved lineups.");
    state.savedLineups = result.lineups || [];
    renderSavedLineups();
  } catch (error) {
    elements.savedLineupList.innerHTML = `<div class="empty-state"><p>${escapeHtml(error.message)}</p></div>`;
  }
}
function loadSavedLineup(record) {
  const data = record?.lineup || {};
  const kind = data.kind || record?.kind;
  if (kind === "random") {
    const lineup = (data.slots || []).map(slot => ({ position: slot.position, card: findCard(slot.card) })).filter(entry => entry.position && entry.card);
    if (lineup.length !== 5) { showSaveToast("This saved random lineup could not be restored.", true); return; }
    state.randomLineup = lineup;
    renderRandomLineupGrid();
    closeSavedLineups();
    elements.lineupModal.classList.add("open");
    elements.lineupModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    showSaveToast("Saved random lineup loaded.");
    return;
  }
  if (kind === "custom") {
    const cards = (data.cards || []).map(findCard).filter(Boolean);
    if (cards.length !== 13) { showSaveToast("This saved custom team could not be restored.", true); return; }
    state.customSelections = cards;
    renderCustomBuilder();
    closeSavedLineups();
    elements.customModal.classList.add("open");
    elements.customModal.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
    showSaveToast("Saved custom team loaded.");
    return;
  }
  const selections = {};
  Object.entries(data.selections || {}).forEach(([key, ref]) => {
    const card = findCard(ref);
    if (card) selections[key] = card;
  });
  const diamond = findCard(data.diamond);
  if (Object.keys(selections).length !== allDraftKeys().length || !diamond) {
    showSaveToast("This saved drafted team could not be restored.", true);
    return;
  }
  state.draftSelections = selections;
  state.draftDiamondSelection = diamond;
  state.draftTarget = null;
  state.draftOptions = [];
  renderDraftGrid();
  closeSavedLineups();
  elements.draftModal.classList.add("open");
  elements.draftModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  showSaveToast("Saved drafted team loaded.");
}
async function deleteSavedLineup(record) {
  if (!record?.path) return;
  try {
    const response = await fetch("/api/delete-saved-lineup", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path: record.path}),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Could not delete saved lineup.");
    state.savedLineups = state.savedLineups.filter(item => item.path !== record.path);
    renderSavedLineups();
    showSaveToast("Saved lineup deleted.");
  } catch (error) {
    showSaveToast(error.message, true);
  }
}

function rosterTrackingKey(path) {
  const roster = (state.injectionState?.rosters || []).find(item => item.path === path);
  return roster?.trackingKey || String(path || "").toLowerCase();
}
function cardForInjection(card) {
  return {
    id: card.id, slug: card.slug, name: card.name, tier: card.tier, overall: card.overall,
    year: card.year, franchise: card.franchise, collection: card.collection, theme: card.theme,
    position: card.position, secondaryPosition: card.secondaryPosition, height: card.height, weight: card.weight,
    age: card.age, badges: card.badges || {}, badgeCounts: card.badgeCounts || {},
    attributes: card.attributes || {}, tendencies: card.tendencies || {}
  };
}
function lineupPackage(kind) {
  if (kind === "random") {
    if (state.randomLineup.length !== 5) return null;
    return state.randomLineup.map(entry => ({
      slot: entry.position, role: "starter", position: entry.position, card: cardForInjection(entry.card)
    }));
  }
  if (kind === "custom") {
    if (state.customSelections.length !== 13) return null;
    return state.customSelections.map((card,index) => ({
      slot: `custom-${index + 1}`, role: index < 5 ? "starter" : index < 12 ? "bench" : "13th pick",
      position: card.position || "FLEX", card: cardForInjection(card)
    }));
  }
  if (!draftComplete() || !state.draftDiamondSelection) return null;
  const players = [];
  ["starter","backup"].forEach(role => {
    lineupPositions.forEach(position => {
      const card = state.draftSelections[slotKey(role, position)];
      if (card) players.push({ slot: `${role}-${position}`, role, position, card: cardForInjection(card) });
    });
  });
  benchRoles.forEach((role,index) => {
    const card = state.draftSelections[benchSlotKey(index + 1)];
    if (card) players.push({ slot: `bench-${index + 1}`, role: "bench", position: "FLEX", card: cardForInjection(card) });
  });
  players.push({ slot: "diamond-round", role: "13th pick", position: state.draftDiamondSelection.position || "FLEX", card: cardForInjection(state.draftDiamondSelection) });
  return players;
}
function closeInjection() {
  elements.injectionModal.classList.remove("open");
  elements.injectionModal.setAttribute("aria-hidden", "true");
  state.injectionKind = null;
  state.injectionTeam = "";
}
function openTeamUnlock(team) {
  state.pendingUnlockTeam = team;
  elements.unlockTeamModal.classList.add("open");
  elements.unlockTeamModal.setAttribute("aria-hidden", "false");
}
function closeTeamUnlock() {
  elements.unlockTeamModal.classList.remove("open");
  elements.unlockTeamModal.setAttribute("aria-hidden", "true");
  state.pendingUnlockTeam = "";
}
function confirmTeamUnlock() {
  if (!state.pendingUnlockTeam) return;
  unlockedTeamsForRoster(state.injectionRosterPath).add(state.pendingUnlockTeam);
  closeTeamUnlock();
  state.injectionTeam = "";
  renderInjectionTeams();
  renderInjectionSummary();
}
function setLoadedRosterStatus(result) {
  state.loadedRosterVerification = result || null;
  state.manualLoadedRosterConfirm = false;
  const verified = Boolean(result?.verified);
  if (elements.confirmLoadedRoster) {
    elements.confirmLoadedRoster.hidden = !(result?.needsManualConfirm && !verified);
  }
  elements.loadedRosterStatus.className = `loaded-roster-status ${verified ? "verified" : "unverified"}`;
  elements.loadedRosterStatus.textContent = result?.message || "Roster has not been verified yet.";
}
function confirmLoadedRosterOpen() {
  const result = state.loadedRosterVerification;
  if (!result?.needsManualConfirm || result?.verified) return;
  state.loadedRosterVerification = {
    ...result,
    verified: true,
    mode: "manual-roster-confirmed",
    message: "Manual confirmation accepted. Injection will use the roster currently open in NBA 2K16."
  };
  state.manualLoadedRosterConfirm = true;
  if (elements.confirmLoadedRoster) elements.confirmLoadedRoster.hidden = true;
  elements.loadedRosterStatus.className = "loaded-roster-status verified";
  elements.loadedRosterStatus.textContent = state.loadedRosterVerification.message;
  renderInjectionSummary();
}
async function verifyLoadedRoster() {
  const roster = selectedRosterRecord();
  if (!roster) {
    setLoadedRosterStatus({ verified: false, message: "Choose a roster file first." });
    renderInjectionSummary();
    return false;
  }
  state.manualLoadedRosterConfirm = false;
  elements.verifyLoadedRoster.disabled = true;
  elements.verifyLoadedRoster.textContent = "Verifying…";
  setLoadedRosterStatus({ verified: false, message: "Checking NBA 2K16 live memory for the selected roster…" });
  try {
    const response = await fetch(`/api/verify-loaded-roster?rosterPath=${encodeURIComponent(roster.path)}`, { cache: "no-store" });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || result.error || "Could not verify the loaded roster.");
    setLoadedRosterStatus(result);
    renderInjectionSummary();
    return Boolean(result.verified);
  } catch (error) {
    setLoadedRosterStatus({
      verified: false,
      needsManualConfirm: true,
      mode: "automatic-verify-failed",
      message: `${error.message} If this exact roster is already open in NBA 2K16, confirm below to inject anyway.`
    });
    renderInjectionSummary();
    return false;
  } finally {
    elements.verifyLoadedRoster.disabled = false;
    elements.verifyLoadedRoster.textContent = "Verify roster is open in 2K16";
  }
}
async function loadInjectionState() {
  const response = await fetch("/api/injection-state", { cache: "no-store" });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "Could not detect rosters.");
  state.injectionState = result;
  return result;
}
async function resetSelectedRosterTracking() {
  const roster = selectedRosterRecord();
  if (!roster) {
    showSaveToast("Choose a roster file first.", true);
    return;
  }
  elements.resetRosterTracking.disabled = true;
  elements.resetRosterTracking.textContent = "Resetting...";
  try {
    const response = await fetch("/api/reset-roster-tracking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rosterPath: roster.path })
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Could not reset this roster.");
    state.injectionTeam = "";
    setLoadedRosterStatus(null);
    await loadInjectionState();
    renderInjectionWizard();
    showSaveToast(result.message || "Selected roster reset.");
  } catch (error) {
    showSaveToast(error.message, true);
  } finally {
    elements.resetRosterTracking.disabled = false;
    elements.resetRosterTracking.textContent = "Reset selected roster";
  }
}
async function saveManualRosterDirectory() {
  const path = elements.manualRosterDir?.value?.trim() || "";
  if (!path) {
    if (elements.manualRosterDirStatus) elements.manualRosterDirStatus.textContent = "Paste the NBA 2K16 folder or OfflineStorage\\User\\remote folder first.";
    showSaveToast("Paste the roster folder first.", true);
    return;
  }
  elements.saveRosterDir.disabled = true;
  elements.saveRosterDir.textContent = "Checking…";
  if (elements.manualRosterDirStatus) elements.manualRosterDirStatus.textContent = "Checking that folder for roster files…";
  try {
    const response = await fetch("/api/set-roster-directory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Could not save that roster folder.");
    state.injectionRosterPath = "";
    state.injectionTeam = "";
    setLoadedRosterStatus(null);
    await loadInjectionState();
    renderInjectionWizard();
    if (elements.manualRosterDir) elements.manualRosterDir.value = result.folder || path;
    if (elements.manualRosterDirStatus) elements.manualRosterDirStatus.textContent = `Using ${result.folder} (${result.count} roster file${result.count === 1 ? "" : "s"} found).`;
    showSaveToast("Roster folder saved. Roster list refreshed.");
  } catch (error) {
    if (elements.manualRosterDirStatus) elements.manualRosterDirStatus.textContent = error.message;
    showSaveToast(error.message, true);
  } finally {
    elements.saveRosterDir.disabled = false;
    elements.saveRosterDir.textContent = "Use this folder";
  }
}
function selectedRosterRecord() {
  const path = state.injectionRosterPath || elements.rosterSelect.value;
  return (state.injectionState?.rosters || []).find(roster => roster.path === path);
}
function usedTeamsForRoster(path) {
  const rosters = state.injectionState?.tracking?.rosters || {};
  let record = rosters[rosterTrackingKey(path)];
  if (!record) {
    const wanted = String(path || "").toLowerCase();
    record = Object.values(rosters).find(item => String(item?.path || "").toLowerCase() === wanted);
  }
  return new Set(Object.entries(record?.teams || {}).filter(([,info]) => info?.status === "live-applied").map(([team]) => team));
}
function unlockedTeamsForRoster(path) {
  const key = rosterTrackingKey(path);
  if (!state.unlockedInjectionTeams[key]) state.unlockedInjectionTeams[key] = new Set();
  return state.unlockedInjectionTeams[key];
}
function renderRosterSelect() {
  const rosters = state.injectionState?.rosters || [];
  const manualDirs = state.injectionState?.settings?.rosterDirectories || [];
  if (elements.manualRosterDir && manualDirs.length && !elements.manualRosterDir.value.trim()) {
    elements.manualRosterDir.value = manualDirs[0];
  }
  if (elements.manualRosterDirStatus) {
    elements.manualRosterDirStatus.textContent = manualDirs.length
      ? `Manual folder active: ${manualDirs[0]}`
      : "Useful if the app is reading the wrong 2K16 roster directory.";
  }
  if (!rosters.length) {
    elements.rosterSelect.innerHTML = `<option value="">No roster files detected yet</option>`;
    elements.rosterHint.textContent = "Create and save a roster in NBA 2K16, or paste the correct roster folder above.";
    state.injectionRosterPath = "";
    return;
  }
  const previous = state.injectionRosterPath;
  elements.rosterSelect.innerHTML = rosters.map((roster,index) => `<option value="${escapeHtml(roster.path)}"${previous ? roster.path === previous ? " selected" : "" : index === 0 ? " selected" : ""}>${escapeHtml(roster.name)} · ${escapeHtml(roster.modifiedText)} · ${escapeHtml(roster.folder)}</option>`).join("");
  state.injectionRosterPath = elements.rosterSelect.value;
  elements.rosterHint.textContent = "Newest rosters appear first. If you just created one in game, it should be at the top.";
  setLoadedRosterStatus(null);
}
function renderInjectionTeams() {
  const historic = state.injectionTeamMode === "historic";
  const teams = historic ? state.injectionState?.classicTeams || [] : state.injectionState?.teams || [];
  const used = usedTeamsForRoster(state.injectionRosterPath);
  if (state.injectionTeam && !teams.includes(state.injectionTeam)) state.injectionTeam = "";
  if (elements.injectionTeamHeading) elements.injectionTeamHeading.textContent = historic ? "2. Choose an NBA Classic team" : "2. Choose an NBA team";
  if (elements.toggleHistoricTeams) elements.toggleHistoricTeams.textContent = historic ? "Switch to NBA teams" : "Switch to historic teams";
  elements.injectionTeamGrid.innerHTML = teams.map(team => {
    const previouslyInjected = used.has(team);
    return `<button class="team-pick${state.injectionTeam === team ? " selected" : ""}${previouslyInjected ? " previously-injected" : ""}" data-injection-team="${escapeHtml(team)}" ${previouslyInjected ? `title="Already injected on this roster; selecting it will overwrite it"` : ""}>${escapeHtml(team)}</button>`;
  }).join("");
}
function renderInjectionSummary() {
  const roster = selectedRosterRecord();
  const players = lineupPackage(state.injectionKind);
  const canSubmit = Boolean(roster && state.injectionTeam && players?.length);
  elements.confirmInjection.disabled = !canSubmit;
  if (!players) {
    elements.injectionSummary.textContent = state.injectionKind === "draft" ? "Finish all 12 draft picks plus the diamond round before injecting." : state.injectionKind === "custom" ? "Pick exactly 13 cards before injecting." : "Generate a random lineup before injecting.";
    return;
  }
  if (!roster) {
    elements.injectionSummary.textContent = "Choose a roster file first.";
    return;
  }
  if (!state.injectionTeam) {
    elements.injectionSummary.innerHTML = `<strong>${escapeHtml(roster.name)}</strong> selected. Choose ${state.injectionTeamMode === "historic" ? "an NBA Classic team" : "an NBA team"}.`;
    return;
  }
  elements.injectionSummary.innerHTML = `Ready to inject <strong>${players.length} players</strong> into <strong>${escapeHtml(state.injectionTeam)}</strong> on <strong>${escapeHtml(roster.name)}</strong>. Keep NBA 2K16 open with that roster loaded, then save in-game after it succeeds.`;
}
function markTeamInjected(rosterPath, team, players, optimistic = false) {
  if (!state.injectionState) state.injectionState = {};
  const key = rosterTrackingKey(rosterPath);
  const tracking = state.injectionState.tracking || (state.injectionState.tracking = { rosters: {} });
  const rosters = tracking.rosters || (tracking.rosters = {});
  const record = rosters[key] || (rosters[key] = { path: rosterPath, teams: {} });
  record.path = rosterPath;
  const teams = record.teams || (record.teams = {});
  teams[team] = {
    status: "live-applied",
    optimistic,
    postWriteVerified: true,
    players: players.map(item => item.card)
  };
}
function unmarkTeamInjected(rosterPath, team) {
  const key = rosterTrackingKey(rosterPath);
  const record = state.injectionState?.tracking?.rosters?.[key];
  if (record?.teams) delete record.teams[team];
}
function renderInjectionWizard() {
  renderRosterSelect();
  renderInjectionTeams();
  renderInjectionSummary();
}
async function openInjection(kind) {
  const players = lineupPackage(kind);
  if (!players) {
    showSaveToast(kind === "draft" || kind === "custom" ? "Your lineup is incomplete" : "Generate a lineup before injecting it.", true);
    return;
  }
  state.injectionKind = kind;
  state.injectionTeam = "";
  elements.injectionModal.classList.add("open");
  elements.injectionModal.setAttribute("aria-hidden", "false");
  elements.injectionSummary.textContent = "Detecting roster files…";
  elements.confirmInjection.disabled = true;
  try {
    await loadInjectionState();
    renderInjectionWizard();
  } catch (error) {
    elements.injectionSummary.textContent = error.message;
    showSaveToast(error.message, true);
  }
}
function prepareInjection() {
  const roster = selectedRosterRecord();
  const players = lineupPackage(state.injectionKind);
  if (!roster || !state.injectionTeam || !players) { renderInjectionSummary(); return; }
  const injectedTeam = state.injectionTeam;
  const rosterPath = roster.path;
  elements.confirmInjection.disabled = true;
  elements.confirmInjection.textContent = "Injecting...";
  markTeamInjected(rosterPath, injectedTeam, players, true);
  renderInjectionTeams();
  renderInjectionSummary();
  const releaseUi = setTimeout(() => {
    closeInjection();
    elements.confirmInjection.textContent = "Inject lineup";
    showSaveToast("Injection is being sent to NBA 2K16...");
  }, 1600);
  const overwriteUnlockedTeam = usedTeamsForRoster(roster.path).has(injectedTeam);
  fetch("/api/prepare-injection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: state.injectionKind,
        rosterPath: roster.path,
        team: injectedTeam,
        players,
        manualLoadedRosterConfirm: state.manualLoadedRosterConfirm,
        overwriteUnlockedTeam
      })
    })
    .then(response => response.json().then(result => ({ response, result })))
    .then(({ response, result }) => {
      if (!response.ok || !result.ok) throw new Error(result.error || "Could not inject lineup.");
      clearTimeout(releaseUi);
      closeInjection();
      elements.confirmInjection.textContent = "Inject lineup";
      if (result.tracking) {
        state.injectionState.tracking = result.tracking;
        renderInjectionTeams();
        renderInjectionSummary();
      }
      showSaveToast(`Injected ${players.length} players into ${injectedTeam}. Save the roster in NBA 2K16.`);
    })
    .catch(error => {
      clearTimeout(releaseUi);
      elements.confirmInjection.disabled = false;
      elements.confirmInjection.textContent = "Inject lineup";
      console.warn("Background injection request finished with an error after the UI was released:", error);
      unmarkTeamInjected(rosterPath, injectedTeam);
      renderInjectionTeams();
      renderInjectionSummary();
      showSaveToast(error.message || "The live injection did not complete.", true);
    });
}

let artWarmupStarted = false;
let draftArtWarmupStarted = false;
function warmDraftArtCache() {
  if (draftArtWarmupStarted || !state.cards.length) return;
  draftArtWarmupStarted = true;
  const tierRank = { Diamond: 0, Amethyst: 1, Gold: 2, Silver: 3, Bronze: 4 };
  const draftPool = state.cards
    .filter(card => lineupPositions.includes(card.position))
    .sort((a,b) => (tierRank[a.tier] ?? 9) - (tierRank[b.tier] ?? 9) || b.overall - a.overall);
  let index = 0;
  const worker = async () => {
    while (index < draftPool.length) {
      const batch = draftPool.slice(index, index + 16);
      index += batch.length;
      await Promise.allSettled(batch.map(card => fetch(artUrl(card, true), { cache: "force-cache" }).catch(() => null)));
      await new Promise(resolve => setTimeout(resolve, 35));
    }
  };
  for (let workerIndex = 0; workerIndex < 4; workerIndex++) worker();
}
async function warmCardArtCache() {
  if (artWarmupStarted || !state.cards.length) return;
  artWarmupStarted = true;
  const seen = new Set();
  const orderedCards = [...state.filtered, ...state.cards].filter(card => {
    const key = `${card.id}/${card.slug}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  let index = 0, completed = 0;
  const total = orderedCards.length;
  showSaveToast(`Caching ${total.toLocaleString()} card images in the background…`);
  const worker = async () => {
    while (index < orderedCards.length) {
      const card = orderedCards[index++];
      try {
        const response = await fetch(artUrl(card), { cache: "force-cache" });
        if (response.ok) await response.blob();
      } catch {}
      completed++;
      if (completed === total) showSaveToast("Card image cache is warmed up. Draft cards should appear much faster now.");
    }
  };
  const concurrency = Math.min(8, total);
  for (let workerIndex = 0; workerIndex < concurrency; workerIndex++) worker();
}

const attributeSections = [
  ["Shooting", [
    "standing_shot_close", "moving_shot_close", "standing_shot_mid", "moving_shot_mid",
    "standing_shot_three", "moving_shot_three", "free_throw", "shot_iq"
  ]],
  ["Inside Scoring", [
    "standing_layup", "driving_layup", "standing_dunk", "driving_dunk", "contact_dunk",
    "draw_foul", "post_control", "post_hook", "post_fadeaway"
  ]],
  ["Playmaking", ["ball_control", "passing_vision", "passing_iq", "passing_accuracy"]],
  ["Defense", [
    "on_ball_defense_iq", "pick_and_roll_defense_iq", "help_defense_iq", "low_post_defense_iq",
    "lateral_quickness", "pass_perception", "reaction_time", "steal", "block",
    "shot_contest", "defensive_consistency"
  ]],
  ["Rebounding", ["boxout", "offensive_rebound", "defensive_rebound"]],
  ["Athleticism", ["speed", "acceleration", "vertical", "strength", "stamina", "hustle", "hands"]],
  ["Consistency, Potential & Durability", [
    "offensive_consistency", "potential", "overall_durability", "head_durability", "neck_durability", "back_durability",
    "left_shoulder_durability", "right_shoulder_durability", "left_elbow_durability",
    "right_elbow_durability", "left_hip_durability", "right_hip_durability",
    "left_knee_durability", "right_knee_durability", "left_ankle_durability",
    "right_ankle_durability", "left_foot_durability", "right_foot_durability",
    "miscellaneous_durability"
  ]]
];
const tendencySections = [
  ["Jump Shooting", [
    "step_through_shot", "shot_under_basket", "shot_close", "shot_close_left",
    "shot_close_middle", "shot_close_right", "shot_mid_range", "shot_mid_range_left",
    "shot_mid_range_left_center", "shot_mid_range_center", "shot_mid_range_right_center",
    "shot_mid_range_right", "shot_three", "shot_three_left", "shot_three_left_center",
    "shot_three_center", "shot_three_right_center", "shot_three_right", "contested_jumper",
    "stepback_jumper", "spin_jumper", "pull_up_in_transition", "use_glass"
  ]],
  ["Layups and Dunks", [
    "standing_layup", "driving_layup", "standing_dunk", "driving_dunk", "flashy_dunk",
    "alley_oop", "putback", "crash", "spin_layup", "hop_step_layup", "euro_step_layup",
    "floater"
  ]],
  ["Drive Setup", [
    "triple_threat_pump_fake", "triple_threat_jab_step", "triple_threat_idle",
    "triple_threat_shoot", "setup_with_sizeup", "setup_with_hesitation", "no_setup_dribble"
  ]],
  ["Driving", [
    "drive", "drive_right", "driving_crossover", "driving_spin", "driving_step_back",
    "driving_half_spin", "driving_double_crossover", "driving_behind_the_back",
    "driving_dribble_hesitation", "driving_in_and_out", "no_driving_dribble_move",
    "attack_strong_on_drive"
  ]],
  ["Passing", ["dish_to_open_man", "flashy_pass", "alley_oop_pass"]],
  ["Post Game", [
    "post_up", "post_shimmy_shot", "post_face_up", "post_back_down",
    "post_aggressive_backdown", "shoot_from_post", "post_hook_left", "post_hook_right",
    "post_fade_left", "post_fade_right", "post_up_and_under", "post_hop_shot",
    "post_step_back_shot", "post_drive", "post_spin", "post_drop_step", "post_hop_step"
  ]],
  ["Freelance", ["shot", "touches", "roll_vs_pop"]],
  ["Defense", [
    "pass_interception", "take_charge", "on_ball_steal", "contest_shot",
    "block_shot", "foul", "hard_foul"
  ]]
];
const attributeKeys = new Set(attributeSections.flatMap(([,keys]) => keys));
const tendencyKeys = new Set(tendencySections.flatMap(([,keys]) => keys));
const ratingAliases = {
  moving_shot_mid_range: "moving_shot_mid",
  standing_shot_mid_range: "standing_shot_mid",
  moving_shot_three_point: "moving_shot_three",
  standing_shot_three_point: "standing_shot_three",
  help_defensive_iq: "help_defense_iq"
};
function valueForKey(attributes, key) {
  if (attributes[key] !== undefined) return attributes[key];
  const alias = Object.entries(ratingAliases).find(([,target]) => target === key)?.[0];
  return alias ? attributes[alias] : undefined;
}
function attributeRow(key, value) {
  const numeric = Number(value);
  const width = Number.isFinite(numeric) ? Math.max(0, Math.min(100, numeric)) : 0;
  return `<div class="attribute-row"><span class="attribute-name">${pretty(key)}</span><span class="attribute-value">${escapeHtml(String(value))}</span><div class="attribute-bar"><div class="attribute-fill" style="width:${width}%"></div></div></div>`;
}
function renderOrderedSections(card, sections, fallbackTitle, allowedKeys = null, dataField = "attributes") {
  const attrs = card[dataField] || {};
  const rendered = new Set();
  const html = sections.map(([title, keys]) => {
    const entries = keys.map(key => [key, valueForKey(attrs, key)]).filter(([,value]) => value !== undefined && value !== null && value !== "");
    entries.forEach(([key]) => rendered.add(key));
    if (!entries.length) return "";
    return `<section class="attribute-section"><h3 class="section-title">${title}</h3><div class="attribute-grid">${entries.map(([key,value]) => attributeRow(key, value)).join("")}</div></section>`;
  }).join("");
  const extras = Object.entries(attrs)
    .filter(([key]) => !rendered.has(key) && (!allowedKeys || allowedKeys.has(key)))
    .sort((a,b) => a[0].localeCompare(b[0]));
  const extraHtml = extras.length ? `<section class="attribute-section"><h3 class="section-title">${fallbackTitle}</h3><div class="attribute-grid">${extras.map(([key,value]) => attributeRow(key, value)).join("")}</div></section>` : "";
  return html + extraHtml;
}
function renderAttributes(card) {
  return renderOrderedSections(card, attributeSections, "Other Attributes", attributeKeys, "attributes") ||
    `<div class="empty-state"><p>No attribute ratings were recovered for this card.</p></div>`;
}
function renderTendencies(card) {
  return renderOrderedSections(card, tendencySections, "Other Tendencies", tendencyKeys, "tendencies") ||
    `<div class="empty-state"><p>No tendency data was recovered for this card.</p></div>`;
}
const personalityBadges = new Set([
  "alpha_dog", "beta_dog", "road_dog", "prime_time", "cool_and_collected", "wildcard",
  "volume_shooter", "closer", "fierce_competitor", "fierce_competition", "spark_plug",
  "swagger", "mind_games", "enforcer", "championship_dna", "mentor", "heart_and_soul",
  "floor_general", "defensive_anchor", "hardened", "gym_rat", "reserved", "friendly",
  "low_ego", "all_time_great", "high_work_ethic", "legendary_work_ethic", "keep_it_real",
  "pat_my_back", "expressive", "unpredictable", "laid_back"
]);

function badgeList(entries, personality = false) {
  if (!entries.length) return "";
  return `<section class="badge-group"><h3 class="section-title">${personality ? "Personality / Mental Badges" : "Skill Badges"}</h3><div class="badge-list">${entries.map(([name,level]) =>
    `<div class="badge ${personality ? "badge-personality" : `badge-level-${level}`}"><span class="badge-medal" aria-hidden="true"></span><strong>${pretty(name)}</strong></div>`
  ).join("")}</div></section>`;
}

function renderBadges(card) {
  const badges = Object.entries(card.badges);
  const skillBadges = badges.filter(([name]) => !personalityBadges.has(name)).sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]));
  const mentalBadges = badges.filter(([name]) => personalityBadges.has(name)).sort((a,b) => a[0].localeCompare(b[0]));
  const derivedCounts = { bronze: 0, silver: 0, gold: 0 };
  skillBadges.forEach(([,level]) => { if (level === 1) derivedCounts.bronze++; else if (level === 2) derivedCounts.silver++; else if (level === 3) derivedCounts.gold++; });
  const totals = ["gold","silver","bronze"].map(level => `<div class="badge-total"><strong>${card.badgeCounts[level] ?? (skillBadges.length ? derivedCounts[level] : "—")}</strong><span>${level}</span></div>`).join("");
  const estimateNote = card.badgesEstimated ? `<div class="estimate-note"><strong>Estimated badge set</strong><span>These badges were generated from the player's attributes and recovered 2K16 MyTEAM badge patterns.</span></div>` : "";
  const list = badges.length ? badgeList(skillBadges) + badgeList(mentalBadges, true)
    : `<div class="empty-state"><p>This archived layout preserved badge totals but not the individual badge names.</p></div>`;
  return `${estimateNote}<div class="badge-summary">${totals}</div><div class="badge-groups">${list}</div>`;
}
function jerseyNumberForCard(card) {
  const overrides = state.jerseyNumberOverrides || {};
  const cardKey = `${card.id}/${card.slug || ""}`;
  const direct = overrides.cards || {};
  if (Number.isFinite(Number(direct[cardKey]))) return Number(direct[cardKey]);
  const name = hotZoneNameKey(card.name);
  const exclusivePlayers = overrides.myteamExclusivePlayers || {};
  if (Number.isFinite(Number(exclusivePlayers[name]))) return Number(exclusivePlayers[name]);
  const resolved = overrides.resolvedCards || {};
  if (Number.isFinite(Number(resolved[cardKey]))) return Number(resolved[cardKey]);
  const year = String(card.year || card.edition || "Current").trim().toLowerCase();
  const franchise = hotZoneNameKey(card.franchise || card.team);
  const combos = overrides.playerTeamYears || {};
  for (const key of [`${name}|${year}|${franchise}`, `${name}|${year}`, `${name}|${franchise}`]) {
    if (Number.isFinite(Number(combos[key]))) return Number(combos[key]);
  }
  const players = overrides.players || {};
  return Number.isFinite(Number(players[name])) ? Number(players[name]) : null;
}

function renderInformation(card) {
  const jerseyNumber = jerseyNumberForCard(card);
  const values = [
    ["Season / edition", card.year || card.edition || "Current"], ["Franchise", card.franchise], ["Collection", card.collection || "—"],
    ["Theme", card.theme || "—"], ["Position", [card.position,card.secondaryPosition].filter(Boolean).join(" / ") || "—"],
    ["Height", card.height || "—"], ["Weight", card.weight ? `${card.weight} lb` : "—"], ["Age", card.age ?? "—"],
    ["From", card.from || "—"], ["Jersey number", jerseyNumber ?? "—"], ["Plays", card.plays || "—"], ["Card ID", card.id]
  ];
  return `<div class="info-grid">${values.map(([label,value]) => `<div class="info-item"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>
    ${card.archiveUrl ? `<a class="archive-link" target="_blank" rel="noreferrer" href="${escapeHtml(card.archiveUrl)}">Open preserved source page ↗</a>` : ""}`;
}

function hotZoneNameKey(name) {
  return String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function hotZoneValues(card) {
  const zones = card.hotZones;
  if (zones && Object.keys(hotZoneSeedPoints).every(key => Number.isInteger(zones[key]))) return zones;
  return state.myteamExclusiveNames.has(hotZoneNameKey(card.name))
    ? Object.fromEntries(Object.keys(hotZoneSeedPoints).map(key => [key, 1]))
    : null;
}

function bucketFillHotZone(pixels, width, height, startX, startY, fillColor) {
  const start = (startY * width + startX) * 4;
  if (pixels[start] !== hotZoneNeutral[0] || pixels[start + 1] !== hotZoneNeutral[1] || pixels[start + 2] !== hotZoneNeutral[2]) return;
  const stack = [[startX, startY]];
  while (stack.length) {
    const [x, y] = stack.pop();
    const index = (y * width + x) * 4;
    if (pixels[index] !== hotZoneNeutral[0] || pixels[index + 1] !== hotZoneNeutral[1] || pixels[index + 2] !== hotZoneNeutral[2]) continue;
    pixels[index] = fillColor[0]; pixels[index + 1] = fillColor[1]; pixels[index + 2] = fillColor[2];
    if (x > 0) stack.push([x - 1, y]);
    if (x + 1 < width) stack.push([x + 1, y]);
    if (y > 0) stack.push([x, y - 1]);
    if (y + 1 < height) stack.push([x, y + 1]);
  }
}

function paintHotZoneChart(canvas, zones) {
  const template = new Image();
  template.onload = () => {
    try {
      canvas.width = template.naturalWidth; canvas.height = template.naturalHeight;
      const context = canvas.getContext("2d", { willReadFrequently: true });
      context.drawImage(template, 0, 0);
      const image = context.getImageData(0, 0, canvas.width, canvas.height);
      for (const [zone, point] of Object.entries(hotZoneSeedPoints)) {
        const stateValue = Number(zones[zone]);
        if (stateValue !== 1) bucketFillHotZone(image.data, canvas.width, canvas.height, point[0], point[1], hotZoneColors[stateValue] || hotZoneNeutral);
      }
      context.putImageData(image, 0, 0);
    } catch (error) {
      showHotZoneRenderError(canvas);
    }
  };
  template.onerror = () => showHotZoneRenderError(canvas);
  template.src = hotZoneTemplateUrl;
}

function showHotZoneRenderError(canvas) {
  const message = document.createElement("div");
  message.className = "empty-state";
  message.innerHTML = "<p>Hot-zone chart artwork could not be loaded.</p>";
  canvas.replaceWith(message);
}

function renderHotZones(card) {
  const zones = hotZoneValues(card);
  if (!zones) return `<div class="empty-state"><p>No scanned hot-zone data was recovered for this card.</p></div>`;
  return `<div class="hot-zone-chart-wrap"><canvas id="hotZoneChart" class="hot-zone-chart" aria-label="${escapeHtml(card.name)} hot zone chart"></canvas></div>`;
}

function renderTab() {
  if (!state.selected) return;
  elements.tabContent.innerHTML = state.tab === "badges" ? renderBadges(state.selected)
    : state.tab === "tendencies" ? renderTendencies(state.selected)
    : state.tab === "information" ? renderInformation(state.selected)
    : state.tab === "hot-zones" ? renderHotZones(state.selected)
    : renderAttributes(state.selected);
  if (state.tab === "hot-zones") {
    const chart = $("#hotZoneChart");
    const zones = hotZoneValues(state.selected);
    if (chart && zones) paintHotZoneChart(chart, zones);
  }
}

async function start() {
  try {
    state.cards = await fetch("data/cards.json?v=2", { cache: "force-cache" }).then(response => { if (!response.ok) throw new Error("Could not load card database"); return response.json(); });
    state.imageManifest = await fetch("data/offline-images.json?v=2", { cache: "force-cache" }).then(response => response.ok ? response.json() : {});
    const jerseyData = await fetch("data/jersey_number_overrides.json?v=2", { cache: "force-cache" }).then(response => response.ok ? response.json() : {});
    state.jerseyNumberOverrides = jerseyData;
    const exclusiveData = await fetch("data/myteam_exclusive_source_overrides.json?v=2", { cache: "force-cache" }).then(response => response.ok ? response.json() : {});
    state.myteamExclusiveNames = new Set(Object.keys(exclusiveData.players || {}).map(hotZoneNameKey));
    addOptions(elements.tier, new Set(state.cards.map(card => card.tier)), tierOrder);
    addOptions(elements.team, new Set(state.cards.filter(card => card.franchise !== "UNASSIGNED").map(card => card.franchise)));
    addOptions(elements.position, new Set(state.cards.flatMap(card => [card.position,card.secondaryPosition])), ["PG","SG","SF","PF","C"]);
    addOptions(elements.theme, new Set(state.cards.map(card => card.theme)));
    addOptions(elements.customTier, new Set(state.cards.map(card => card.tier)), tierOrder);
    addOptions(elements.customPosition, new Set(state.cards.flatMap(card => [card.position,card.secondaryPosition])), ["PG","SG","SF","PF","C"]);
    addOptions(elements.customTeam, new Set(state.cards.filter(card => card.franchise !== "UNASSIGNED").map(card => card.franchise)));
    applyFilters();
    setTimeout(warmDraftArtCache, 150);
    openStartupMode();
  } catch (error) { elements.resultTitle.textContent = "Viewer failed to load"; elements.grid.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
}

function openStartupMode() {
  const mode = new URLSearchParams(window.location.search).get("mode");
  if (mode === "draft") openDraft();
  else if (mode === "random") createRandomLineup();
  else if (mode === "custom") openCustomTeam();
  else if (mode === "inject") showSaveToast("Create or load a lineup first, then choose Inject into roster.", true);
}

[elements.tier,elements.team,elements.position,elements.theme,elements.overall,elements.sort].forEach(element => element.addEventListener("change", applyFilters));
elements.search.addEventListener("input", debounce(applyFilters));
elements.grid.addEventListener("click", event => { const tile = event.target.closest(".card-tile"); if (!tile) return; const [id,...slug] = tile.dataset.cardKey.split("/"); const card = state.cards.find(card => String(card.id) === id && card.slug === slug.join("/")); const image = tile.querySelector("img"); if (card) openCard(card, image?.currentSrc || image?.src || ""); });
elements.loadMore.addEventListener("click", () => { state.visible += 48; renderCards(); });
elements.activeFilters.addEventListener("click", event => { const pill = event.target.closest("[data-clear]"); if (pill) clearFilter(pill.dataset.clear); });
$("#clearFilters").addEventListener("click", clearAllFilters); $("#mobileFilter").addEventListener("click", () => elements.filters.classList.toggle("mobile-open"));
$("#randomTeam").addEventListener("click", createRandomLineup); $("#rerollTeam").addEventListener("click", createRandomLineup);
$("#draftTeam").addEventListener("click", openDraft);
$("#customTeam").addEventListener("click", openCustomTeam);
$("#clearDraft").addEventListener("click", () => { state.draftSelections = {}; state.draftDiamondSelection = null; renderDraftGrid(); });
$$("[data-draft-mode]").forEach(button => button.addEventListener("click", () => setDraftMode(button.dataset.draftMode)));
$("#saveRandomLineup").addEventListener("click", () => saveLineup("random"));
$("#saveDraftLineup").addEventListener("click", () => saveLineup("draft"));
$("#saveCustomLineup").addEventListener("click", () => saveLineup("custom"));
$("#loadRandomLineup").addEventListener("click", () => openSavedLineups("random"));
$("#loadDraftLineup").addEventListener("click", () => openSavedLineups("draft"));
$("#loadCustomLineup").addEventListener("click", () => openSavedLineups("custom"));
$("#injectRandomLineup").addEventListener("click", () => openInjection("random"));
$("#injectDraftLineup").addEventListener("click", () => openInjection("draft"));
$("#injectCustomLineup").addEventListener("click", () => openInjection("custom"));
$("#clearCustomTeam").addEventListener("click", () => { state.customSelections = []; renderCustomBuilder(); });
elements.customSearch.addEventListener("input", debounce(applyCustomFilters));
elements.customTier.addEventListener("change", applyCustomFilters);
elements.customPosition.addEventListener("change", applyCustomFilters);
elements.customTeam.addEventListener("change", applyCustomFilters);
elements.customSelectedGrid.addEventListener("click", event => {
  const remove = event.target.closest("[data-remove-custom]");
  if (!remove) return;
  state.customSelections.splice(Number(remove.dataset.removeCustom), 1);
  renderCustomBuilder();
});
elements.customPickerGrid.addEventListener("click", event => {
  const add = event.target.closest("[data-add-custom]");
  if (!add || state.customSelections.length >= 13) return;
  const card = state.customFiltered[Number(add.dataset.addCustom)];
  if (!card) return;
  state.customSelections.push(card);
  renderCustomBuilder();
});
$("#refreshRosters").addEventListener("click", async () => {
  try { setLoadedRosterStatus(null); await loadInjectionState(); renderInjectionWizard(); showSaveToast("Roster list refreshed."); }
  catch (error) { showSaveToast(error.message, true); }
});
elements.saveRosterDir.addEventListener("click", saveManualRosterDirectory);
elements.manualRosterDir.addEventListener("keydown", event => {
  if (event.key === "Enter") saveManualRosterDirectory();
});
elements.rosterSelect.addEventListener("change", () => { state.injectionRosterPath = elements.rosterSelect.value; state.injectionTeam = ""; setLoadedRosterStatus(null); renderInjectionTeams(); renderInjectionSummary(); });
elements.verifyLoadedRoster.addEventListener("click", verifyLoadedRoster);
elements.resetRosterTracking.addEventListener("click", resetSelectedRosterTracking);
elements.confirmLoadedRoster.addEventListener("click", confirmLoadedRosterOpen);
if (elements.toggleHistoricTeams) elements.toggleHistoricTeams.addEventListener("click", () => {
  state.injectionTeamMode = state.injectionTeamMode === "historic" ? "nba" : "historic";
  state.injectionTeam = "";
  renderInjectionTeams();
  renderInjectionSummary();
});
elements.injectionTeamGrid.addEventListener("click", event => {
  const team = event.target.closest("[data-injection-team]");
  if (!team) return;
  state.injectionTeam = team.dataset.injectionTeam;
  renderInjectionTeams();
  renderInjectionSummary();
});
elements.confirmInjection.addEventListener("click", prepareInjection);
elements.injectionModal.addEventListener("click", event => { if (event.target.closest("[data-close-injection]")) closeInjection(); });
$("#cancelTeamUnlock").addEventListener("click", closeTeamUnlock);
elements.confirmTeamUnlock.addEventListener("click", confirmTeamUnlock);
elements.unlockTeamModal.addEventListener("click", event => { if (event.target.closest("[data-cancel-team-unlock]")) closeTeamUnlock(); });
elements.savedLineupModal.addEventListener("click", event => {
  if (event.target.closest("[data-close-saved-lineups]")) { closeSavedLineups(); return; }
  const deletion = event.target.closest("[data-delete-saved]");
  if (deletion) {
    const records = state.savedLineups.filter(item => item.kind === state.savedLineupKind);
    deleteSavedLineup(records[Number(deletion.dataset.deleteSaved)]);
    return;
  }
  const picked = event.target.closest("[data-load-saved]");
  if (!picked) return;
  const records = state.savedLineups.filter(item => item.kind === state.savedLineupKind);
  loadSavedLineup(records[Number(picked.dataset.loadSaved)]);
});
elements.customModal.addEventListener("click", event => { if (event.target.closest("[data-close-custom]")) closeCustomTeam(); });
elements.modal.addEventListener("click", event => { if (event.target.closest("[data-close-modal]")) closeModal(); });
elements.lineupModal.addEventListener("click", event => {
  if (event.target.closest("[data-close-lineup]")) { closeLineup(); return; }
  const tile = event.target.closest(".lineup-card");
  if (!tile) return;
  const [id,...slug] = tile.dataset.cardKey.split("/");
  const card = state.cards.find(card => String(card.id) === id && card.slug === slug.join("/"));
  if (card) {
    state.returnToLineup = true;
    elements.lineupModal.classList.remove("open");
    elements.lineupModal.setAttribute("aria-hidden", "true");
    openCard(card, tile.querySelector("img")?.currentSrc || tile.querySelector("img")?.src || "");
  }
});
elements.draftModal.addEventListener("click", event => {
  if (event.target.closest("[data-close-draft]")) { closeDraft(); return; }
  if (event.target.closest("#startDiamondRound")) { openDiamondRoundChoices(); return; }
  if (event.target.closest("#returnDiamondChoices")) { openDiamondRoundChoices(); return; }
  const view = event.target.closest("[data-view-card]");
  if (view) {
    const [id,...slug] = view.dataset.viewCard.split("/");
    const card = state.cards.find(card => String(card.id) === id && card.slug === slug.join("/"));
    const image = view.closest("[data-view-card], .draft-slot, .diamond-round-card")?.querySelector("img");
    if (card) openCardFromDraft(card, false, image?.currentSrc || image?.src || "");
    return;
  }
  const slot = event.target.closest("[data-draft-slot]");
  if (slot) openDraftChoices(slot.dataset.draftSlot);
});
elements.draftChoiceModal.addEventListener("click", event => {
  if (event.target.closest("#viewLineupFromChoices")) {
    elements.draftChoiceModal.classList.remove("open");
    elements.draftChoiceModal.setAttribute("aria-hidden", "true");
    renderDraftGrid();
    return;
  }
  const preview = event.target.closest("[data-choice-view]");
  if (preview && state.draftTarget) {
    const card = state.draftOptions[Number(preview.dataset.choiceView)];
    const image = preview.closest(".draft-choice-card")?.querySelector("img");
    if (card) openCardFromDraft(card, true, image?.currentSrc || image?.src || "");
    return;
  }
  const choice = event.target.closest("[data-choice-index]");
  if (!choice || !state.draftTarget) return;
  const card = state.draftOptions[Number(choice.dataset.choiceIndex)];
  if (card && state.draftTarget === "diamond-round") {
    state.draftDiamondSelection = card;
  } else if (card) state.draftSelections[state.draftTarget] = card;
  closeDraftChoices(); renderDraftGrid(); setTimeout(() => focusNextDraftTarget(), 60);
});
$(".tabs").addEventListener("click", event => { const tab = event.target.closest(".tab"); if (!tab) return; state.tab = tab.dataset.tab; $$(".tab").forEach(item => item.classList.toggle("active", item === tab)); renderTab(); });
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && elements.draftChoiceModal.classList.contains("open")) return;
  else if (event.key === "Escape" && elements.unlockTeamModal.classList.contains("open")) closeTeamUnlock();
  else if (event.key === "Escape" && elements.savedLineupModal.classList.contains("open")) closeSavedLineups();
  else if (event.key === "Escape" && state.selected) closeModal();
  else if (event.key === "Escape" && elements.injectionModal.classList.contains("open")) closeInjection();
  else if (event.key === "Escape" && elements.customModal.classList.contains("open")) closeCustomTeam();
  else if (event.key === "Escape" && elements.lineupModal.classList.contains("open")) closeLineup();
  else if (event.key === "Escape" && elements.draftModal.classList.contains("open")) closeDraft();
  if (event.key === "/" && !state.selected && !elements.lineupModal.classList.contains("open") && !elements.draftModal.classList.contains("open") && !elements.customModal.classList.contains("open") && document.activeElement !== elements.search) { event.preventDefault(); elements.search.focus(); }
});
start();
