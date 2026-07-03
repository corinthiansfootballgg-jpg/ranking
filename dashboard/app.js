// CAMINHOS CORRIGIDOS PARA SUBIR UM NÍVEL DA PASTA DASHBOARD
const DATA_URL = '../data/ranking.json';
const HISTORY_URL = '../data/history.json';
const CHART_COLORS = [
  "#ff4d2e", "#ff8c42", "#ffd166", "#3dd68c", "#4ecdc4",
  "#a78bfa", "#f472b6", "#60a5fa", "#fbbf24", "#34d399",
];

let data = null;
const charts = {};

function formatNumber(n) {
  return (n ?? 0).toLocaleString("pt-BR");
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function allTeams() {
  if (!data?.clas) return [];
  return data.clas.flatMap((cla) =>
    cla.times.map((t) => ({ ...t, cla_grupo: cla.nome }))
  );
}

function chartDefaults() {
  return {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#1a1d28",
        titleColor: "#f0f2f8",
        bodyColor: "#8b92a8",
        borderColor: "rgba(255,255,255,0.1)",
        borderWidth: 1,
        padding: 12,
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(255,255,255,0.05)" },
        ticks: { color: "#8b92a8", maxRotation: 45 },
      },
      y: {
        grid: { color: "rgba(255,255,255,0.05)" },
        ticks: { color: "#8b92a8" },
      },
    },
  };
}

function destroyChart(id) {
  if (charts[id]) {
    charts[id].destroy();
    delete charts[id];
  }
}

function barChart(id, labels, values, label) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return;
  charts[id] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label,
        data: values,
        backgroundColor: labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length] + "cc"),
        borderColor: labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]),
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: chartDefaults(),
  });
}

function horizontalBarChart(id, items, valueKey, label) {
  const top = items.slice(0, 10);
  barChart(
    id,
    top.map((t) => t.nome.length > 18 ? t.nome.slice(0, 16) + "…" : t.nome),
    top.map((t) => t[valueKey]),
    label
  );
}

function renderOverview() {
  const teams = allTeams();
  const stats = data.stats || {};

  document.getElementById("total-teams").textContent = teams.length;
  document.getElementById("total-clas").textContent = data.clas.length;
  document.getElementById("meses-historico").textContent =
    stats.meses_historico_disponiveis ?? 0;

  const top = stats.maior_pontuador_mensal;
  if (top) {
    document.getElementById("top-scorer-name").textContent = top.nome;
    document.getElementById("top-scorer-points").textContent =
      formatNumber(top.geral_mensal) + " pts";
    document.getElementById("top-scorer-cla").textContent =
      `${top.cla_grupo || top.cla} · ${formatNumber(top.pontos_ano)} pts no ano`;
  }

  const byAno = [...teams].sort((a, b) => b.pontos_ano - a.pontos_ano);
  const byMensal = [...teams].sort((a, b) => b.geral_mensal - a.geral_mensal);
  horizontalBarChart("chart-ano", byAno, "pontos_ano", "Pontos Ano");
  horizontalBarChart("chart-mensal", byMensal, "geral_mensal", "Geral Mensal");

  const porCla = data.clas.map((cla) => ({
    nome: cla.nome,
    total: cla.times.reduce((s, t) => s + t.pontos_ano, 0),
  })).sort((a, b) => b.total - a.total);

  destroyChart("chart-clas");
  const ctxClas = document.getElementById("chart-clas");
  if (ctxClas) {
    charts["chart-clas"] = new Chart(ctxClas, {
      type: "doughnut",
      data: {
        labels: porCla.map((c) => c.nome),
        datasets: [{
          data: porCla.map((c) => c.total),
          backgroundColor: porCla.map((_, i) => CHART_COLORS[i % CHART_COLORS.length] + "dd"),
          borderColor: "#12141c",
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: "right",
            labels: { color: "#8b92a8", padding: 12, font: { family: "Outfit" } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${formatNumber(ctx.raw)} pts`,
            },
          },
        },
      },
    });
  }
}

function renderClas() {
  const select = document.getElementById("cla-select");
  select.innerHTML = data.clas
    .map((c, i) => `<option value="${i}">${c.nome} (${c.times.length} times)</option>`)
    .join("");

  function showCla(index) {
    const cla = data.clas[index];
    document.getElementById("cla-table-title").textContent = cla.nome;
    document.getElementById("cla-table-body").innerHTML = cla.times
      .map((t) => `
        <tr>
          <td>${t.posicao}</td>
          <td><strong>${t.nome}</strong></td>
          <td class="num">${formatNumber(t.pontos_ano)}</td>
          <td class="num">${formatNumber(t.geral_mensal)}</td>
          <td>${t.cla}</td>
        </tr>
      `)
      .join("");
  }

  select.onchange = () => showCla(Number(select.value));
  showCla(0);
}

function renderRankingList(elId, teams, field) {
  const el = document.getElementById(elId);
  el.innerHTML = teams.slice(0, 15).map((t) => `
    <li>
      <div class="rank-name">${t.nome}</div>
      <div class="rank-meta">${t.cla_grupo || t.cla}</div>
      <div class="rank-points">${formatNumber(t[field])}</div>
    </li>
  `).join("");
}

function renderRankings() {
  const teams = allTeams();
  renderRankingList(
    "ranking-ano",
    [...teams].sort((a, b) => b.pontos_ano - a.pontos_ano),
    "pontos_ano"
  );
  renderRankingList(
    "ranking-mensal",
    [...teams].sort((a, b) => b.geral_mensal - a.geral_mensal),
    "geral_mensal"
  );
}

function renderMediaTable(elId, items) {
  document.getElementById(elId).innerHTML = items.slice(0, 15).map((t, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><strong>${t.nome}</strong></td>
      <td>${t.cla_grupo || t.cla}</td>
      <td class="num">${formatNumber(t.media)}</td>
      <td>${t.meses_considerados}</td>
    </tr>
  `).join("");
}

function renderMedias() {
  const stats = data.stats || {};
  const meses = stats.meses_historico_disponiveis ?? 0;
  const info = document.getElementById("medias-info");

  if (meses < 2) {
    info.textContent =
      "As médias de 3 e 6 meses ficam mais precisas conforme o script roda mensalmente. " +
      `Atualmente há ${meses} mês(es) de histórico salvo.`;
  } else {
    info.textContent =
      `Médias calculadas com base nos últimos snapshots mensais (${meses} meses no histórico).`;
  }

  const m3 = stats.media_3_meses || [];
  const m6 = stats.media_6_meses || [];

  horizontalBarChart("chart-media-3", m3, "media", "Média 3 meses");
  horizontalBarChart("chart-media-6", m6, "media", "Média 6 meses");
  renderMediaTable("table-media-3", m3);
  renderMediaTable("table-media-6", m6);
}

function renderTitulos() {
  const titulos = data.stats?.titulos_recentes || [];
  const grid = document.getElementById("titulos-grid");
  const empty = document.getElementById("titulos-empty");

  if (!titulos.length) {
    grid.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");
  grid.innerHTML = titulos.map((t) => `
    <article class="titulo-card">
      <div class="trophy">🏆</div>
      <h4>${t.competicao}</h4>
      <div class="time-name">${t.time}</div>
      <div class="meta">
        ${t.cla_grupo || t.cla}
        ${t.data ? ` · ${t.data}` : ""}
        ${t.temporada ? ` · Temp. ${t.temporada}` : ""}
      </div>
    </article>
  `).join("");
}

function setupTabs() {
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      document.getElementById(`panel-${tab.dataset.tab}`).classList.add("active");
    });
  });
}

async function load() {
  try {
    const res = await fetch(DATA_URL);
    if (!res.ok) throw new Error(`Erro no ranking: ${res.status}`);
    data = await res.json();

    try {
      const resHist = await fetch(HISTORY_URL); // Usando a constante corrigida
      if (resHist.ok) {
        const historyData = await resHist.json();
        data.history = historyData; 
      }
    } catch (e) {
      console.warn("Histórico não carregado.");
    }

    document.getElementById("mes-referencia").textContent = data.mes_referencia || "—";
    document.getElementById("updated-at").textContent = "Atualizado em " + formatDate(data.updated_at);

    renderOverview();
    renderClas();
    renderRankings();
    renderMedias();
    renderTitulos();
    setupTabs();

  } catch (err) {
    document.getElementById("updated-at").textContent = "Erro ao carregar dados.";
    console.error(err);
  }
}
load();