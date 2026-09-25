const title = document.querySelector("#selected-title");
const flags = document.querySelector("#selected-flags");
const code = document.querySelector(".sql-code code");
const queryList = document.querySelector("#query-list");
const queryCount = document.querySelector("#query-count");
const queryStatus = document.querySelector("#query-status");
const querySearch = document.querySelector("#query-search");
const resultCount = document.querySelector("#result-count");
const resultsContainer = document.querySelector("#results-container");
const whyItMatters = document.querySelector("#why-it-matters");
const nextStep = document.querySelector("#next-step");
const queryLibraryTotal = document.querySelector("#query-library-total");
const watchlistCount = document.querySelector("#watchlist-count");
const watchlistContainer = document.querySelector("#watchlist-container");
const scoreChart = document.querySelector("#score-chart");
const customSql = document.querySelector("#custom-sql");
const runCustomSqlButton = document.querySelector("#run-custom-sql");
const customSqlStatus = document.querySelector("#custom-sql-status");
const customResultsArea = document.querySelector("#custom-results-area");
const customResultCount = document.querySelector("#custom-result-count");
const customResults = document.querySelector("#custom-results");

let availableQueries = [];
let selectedQuery = null;

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || `Request failed with status ${response.status}`);
  }
  return payload;
}

function queryButton(query, index) {
  const button = document.createElement("button");
  button.className = `query-item${query.name === selectedQuery ? " active" : ""}`;
  button.type = "button";
  button.dataset.query = query.name;

  const icon = document.createElement("span");
  icon.className = "query-icon";
  icon.textContent = String(index + 1).padStart(2, "0");

  const details = document.createElement("span");
  details.className = "query-item-details";
  const titleLine = document.createElement("span");
  titleLine.className = "query-title-line";
  const name = document.createElement("strong");
  name.textContent = query.title;
  const severity = document.createElement("span");
  severity.className = `severity-badge ${query.severity.toLowerCase()}`;
  severity.textContent = query.severity;
  severity.title = query.severity_reason;
  const category = document.createElement("small");
  category.textContent = query.category;
  titleLine.append(name, severity);
  details.append(titleLine, category);
  button.append(icon, details);
  button.addEventListener("click", () => loadQuery(query.name));
  return button;
}

function renderQueryList(filter = "") {
  const normalizedFilter = filter.trim().toLowerCase();
  const filtered = availableQueries.filter((query) =>
    `${query.title} ${query.category} ${query.severity} ${query.description}`
      .toLowerCase()
      .includes(normalizedFilter),
  );
  queryList.replaceChildren();
  const categories = [...new Set(filtered.map((query) => query.category))];
  categories.forEach((category) => {
    const heading = document.createElement("div");
    heading.className = "query-category-heading";
    heading.textContent = category;
    queryList.append(heading);
    filtered.filter((query) => query.category === category).forEach((query) => {
      const originalIndex = availableQueries.findIndex((item) => item.name === query.name);
      queryList.append(queryButton(query, originalIndex));
    });
  });
  if (!filtered.length) {
    const message = document.createElement("div");
    message.className = "remaining-note";
    message.textContent = "No checks match this filter.";
    queryList.append(message);
  }
}

function displayValue(column, value) {
  if (value === null || value === undefined) return "Not available";
  if (column.endsWith("_amount_cents")) {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value / 100);
  }
  if (column.endsWith("_rate")) return `${(value * 100).toFixed(2)}%`;
  if (typeof value === "number") return value.toLocaleString("en-US");
  return String(value);
}

function renderResults(data) {
  resultCount.textContent = `${data.row_count} ${data.row_count === 1 ? "row" : "rows"}`;
  resultsContainer.className = "results-content";
  resultsContainer.replaceChildren();

  if (!data.rows.length) {
    resultsContainer.className = "empty-state";
    const heading = document.createElement("strong");
    heading.textContent = "No merchants matched";
    const detail = document.createElement("p");
    detail.textContent = "The query completed successfully with no results.";
    resultsContainer.append(heading, detail);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "table-scroll";
  const table = document.createElement("table");
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  data.columns.forEach((column) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column.replaceAll("_", " ");
    headerRow.append(cell);
  });
  header.append(headerRow);

  const body = document.createElement("tbody");
  data.rows.forEach((row) => {
    const tableRow = document.createElement("tr");
    data.columns.forEach((column) => {
      const cell = document.createElement("td");
      cell.textContent = displayValue(column, row[column]);
      tableRow.append(cell);
    });
    body.append(tableRow);
  });
  table.append(header, body);
  wrapper.append(table);
  resultsContainer.append(wrapper);
}

function showError(message) {
  queryStatus.textContent = "Query unavailable.";
  resultCount.textContent = "Error";
  resultsContainer.className = "empty-state";
  resultsContainer.replaceChildren();
  const heading = document.createElement("strong");
  heading.textContent = "Could not load query";
  const detail = document.createElement("p");
  detail.textContent = message;
  resultsContainer.append(heading, detail);
}

async function loadQuery(queryName) {
  selectedQuery = queryName;
  renderQueryList(querySearch.value);
  queryStatus.textContent = "Running against the read-only database...";
  resultCount.textContent = "Loading...";
  try {
    const data = await fetchJson(`/api/queries/${encodeURIComponent(queryName)}`);
    title.textContent = data.title;
    flags.textContent = data.description;
    whyItMatters.textContent = data.why_it_matters;
    nextStep.textContent = data.next_step;
    code.textContent = data.sql;
    queryStatus.textContent = "Completed through a read-only DuckDB connection.";
    renderResults(data);
  } catch (error) {
    showError(error.message);
  }
}

async function initializeQueries() {
  try {
    availableQueries = await fetchJson("/api/queries");
    queryCount.textContent = `${availableQueries.length} available`;
    queryLibraryTotal.textContent = availableQueries.length;
    renderQueryList();
    if (availableQueries.length) {
      await loadQuery(availableQueries[0].name);
    }
  } catch (error) {
    queryCount.textContent = "Unavailable";
    showError(error.message);
  }
}

function toggleWatchlistDetails(entryRow, detailsRow) {
  const expanded = entryRow.getAttribute("aria-expanded") === "true";
  entryRow.setAttribute("aria-expanded", String(!expanded));
  detailsRow.hidden = expanded;
}

function renderWatchlist(merchants) {
  watchlistCount.textContent = `${merchants.length} flagged`;
  watchlistContainer.className = "watchlist-table-wrap";
  watchlistContainer.replaceChildren();

  const table = document.createElement("table");
  table.className = "watchlist-table";
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["Rank", "Merchant and reasons", "Score"].forEach((label) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    headerRow.append(cell);
  });
  header.append(headerRow);

  const body = document.createElement("tbody");
  merchants.forEach((merchant) => {
    const entryRow = document.createElement("tr");
    entryRow.className = "watchlist-entry";
    entryRow.dataset.merchantId = merchant.merchant_id;
    entryRow.tabIndex = 0;
    entryRow.setAttribute("role", "button");
    entryRow.setAttribute("aria-expanded", "false");

    const rankCell = document.createElement("td");
    const rank = document.createElement("span");
    rank.className = "rank";
    rank.textContent = merchant.rank;
    rankCell.append(rank);

    const merchantCell = document.createElement("td");
    const merchantName = document.createElement("strong");
    merchantName.textContent = merchant.merchant_name;
    const merchantId = document.createElement("small");
    merchantId.textContent = merchant.merchant_id;
    const chips = document.createElement("div");
    chips.className = "chips";
    merchant.reason_chips.forEach((reasonTitle) => {
      const chip = document.createElement("span");
      chip.textContent = reasonTitle;
      chips.append(chip);
    });
    merchantCell.append(merchantName, merchantId, chips);

    const scoreCell = document.createElement("td");
    const score = document.createElement("span");
    score.className = "watchlist-score";
    score.textContent = merchant.score;
    scoreCell.append(score);
    entryRow.append(rankCell, merchantCell, scoreCell);

    const detailsRow = document.createElement("tr");
    detailsRow.className = "watchlist-evidence-row";
    detailsRow.hidden = true;
    const detailsCell = document.createElement("td");
    detailsCell.colSpan = 3;
    merchant.triggered_queries.forEach((query) => {
      const detail = document.createElement("div");
      detail.className = "watchlist-evidence";
      const detailTitle = document.createElement("strong");
      detailTitle.textContent = `${query.title} (+${query.weight})`;
      const detailReason = document.createElement("p");
      detailReason.textContent = query.reason;
      detail.append(detailTitle, detailReason);
      detailsCell.append(detail);
    });
    detailsRow.append(detailsCell);

    entryRow.addEventListener("click", () => toggleWatchlistDetails(entryRow, detailsRow));
    entryRow.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggleWatchlistDetails(entryRow, detailsRow);
      }
    });
    body.append(entryRow, detailsRow);
  });

  table.append(header, body);
  watchlistContainer.append(table);
}

function svgElement(name, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function selectWatchlistMerchant(merchantId) {
  document.querySelectorAll(".watchlist-entry").forEach((row) => {
    row.classList.toggle("selected", row.dataset.merchantId === merchantId);
  });
  document.querySelectorAll(".score-bar-group").forEach((bar) => {
    bar.classList.toggle("selected", bar.dataset.merchantId === merchantId);
  });
  const selectedRow = [...document.querySelectorAll(".watchlist-entry")].find(
    (row) => row.dataset.merchantId === merchantId,
  );
  if (selectedRow) {
    selectedRow.scrollIntoView({ behavior: "smooth", block: "nearest" });
    selectedRow.focus({ preventScroll: true });
  }
}

function renderScoreChart(chartData) {
  scoreChart.className = "score-chart-wrap";
  scoreChart.replaceChildren();
  if (!chartData.length) {
    scoreChart.className = "score-chart-loading";
    scoreChart.textContent = "No flagged merchants to chart.";
    return;
  }

  const width = 480;
  const leftMargin = 72;
  const rightMargin = 38;
  const topMargin = 12;
  const rowHeight = 26;
  const barHeight = 16;
  const height = topMargin + chartData.length * rowHeight + 10;
  const maximumScore = Math.max(...chartData.map((merchant) => merchant.score));
  const chartWidth = width - leftMargin - rightMargin;
  const svg = svgElement("svg", {
    class: "score-chart",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-labelledby": "score-chart-title score-chart-description",
  });
  const chartTitle = svgElement("title", { id: "score-chart-title" });
  chartTitle.textContent = "Watchlist score distribution";
  const chartDescription = svgElement("desc", { id: "score-chart-description" });
  chartDescription.textContent = "Flagged merchants ranked by weighted query score.";
  svg.append(chartTitle, chartDescription);

  chartData.forEach((merchant, index) => {
    const y = topMargin + index * rowHeight;
    const barWidth = Math.max(2, (merchant.score / maximumScore) * chartWidth);
    const group = svgElement("g", {
      class: "score-bar-group",
      role: "button",
      tabindex: "0",
      "aria-label": `${merchant.merchant_id}, score ${merchant.score}`,
    });
    group.dataset.merchantId = merchant.merchant_id;

    const merchantLabel = svgElement("text", {
      class: "score-chart-merchant",
      x: "8",
      y: String(y + 12),
    });
    merchantLabel.textContent = merchant.merchant_id;
    const bar = svgElement("rect", {
      class: "score-chart-bar",
      x: String(leftMargin),
      y: String(y),
      width: String(barWidth),
      height: String(barHeight),
      rx: "4",
    });
    const scoreLabel = svgElement("text", {
      class: "score-chart-value",
      x: String(leftMargin + barWidth + 6),
      y: String(y + 12),
    });
    scoreLabel.textContent = merchant.score;
    group.append(merchantLabel, bar, scoreLabel);
    group.addEventListener("click", () => selectWatchlistMerchant(merchant.merchant_id));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectWatchlistMerchant(merchant.merchant_id);
      }
    });
    svg.append(group);
  });
  scoreChart.append(svg);
}

async function initializeWatchlist() {
  try {
    const [merchants, chartData] = await Promise.all([
      fetchJson("/api/watchlist"),
      fetchJson("/api/watchlist/chart"),
    ]);
    renderWatchlist(merchants);
    renderScoreChart(chartData);
  } catch (error) {
    watchlistCount.textContent = "Unavailable";
    watchlistContainer.className = "watchlist-loading";
    watchlistContainer.textContent = `Could not load watchlist: ${error.message}`;
    scoreChart.className = "score-chart-loading";
    scoreChart.textContent = "Could not load score distribution.";
  }
}

function renderCustomResults(data) {
  customResultsArea.hidden = false;
  customResultCount.textContent = `${data.row_count} ${data.row_count === 1 ? "row" : "rows"}`;
  customResults.replaceChildren();

  if (!data.rows.length) {
    const empty = document.createElement("div");
    empty.className = "custom-empty";
    empty.textContent = "The query completed with no rows.";
    customResults.append(empty);
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "table-scroll";
  const table = document.createElement("table");
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  data.columns.forEach((column) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column.replaceAll("_", " ");
    headerRow.append(cell);
  });
  header.append(headerRow);

  const body = document.createElement("tbody");
  data.rows.forEach((row) => {
    const tableRow = document.createElement("tr");
    data.columns.forEach((column) => {
      const cell = document.createElement("td");
      cell.textContent = displayValue(column, row[column]);
      tableRow.append(cell);
    });
    body.append(tableRow);
  });
  table.append(header, body);
  wrapper.append(table);
  customResults.append(wrapper);
}

async function runCustomQuery() {
  const sql = customSql.value.trim();
  if (!sql) return;
  runCustomSqlButton.disabled = true;
  customSql.disabled = true;
  customSqlStatus.classList.remove("error-text");
  customSqlStatus.textContent = "Running in the restricted read-only database...";
  try {
    const data = await fetchJson("/api/custom-query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql }),
    });
    renderCustomResults(data);
    customSqlStatus.textContent = data.truncated
      ? `Showing the first ${data.row_limit} rows. Additional rows were truncated.`
      : `Query completed with ${data.row_count} ${data.row_count === 1 ? "row" : "rows"}.`;
  } catch (error) {
    customResultsArea.hidden = true;
    customSqlStatus.classList.add("error-text");
    customSqlStatus.textContent = error.message;
  } finally {
    customSql.disabled = false;
    runCustomSqlButton.disabled = !customSql.value.trim();
  }
}

querySearch.addEventListener("input", () => renderQueryList(querySearch.value));
customSql.addEventListener("input", () => {
  runCustomSqlButton.disabled = !customSql.value.trim();
});
runCustomSqlButton.addEventListener("click", runCustomQuery);

initializeQueries();
initializeWatchlist();
