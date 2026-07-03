from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import gspread
import time
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from oauth2client.service_account import ServiceAccountCredentials

# =========================================================
# CONFIGURAÇÕES
# =========================================================
LOGIN = os.environ.get("GAMEGOL_LOGIN", "josewender31")
SENHA = os.environ.get("GAMEGOL_SENHA")
PLANILHA_NOME = os.environ.get("PLANILHA_NOME", "Tabela times FRCF")
DATA_DIR = Path(__file__).resolve().parent / "data"
RANKING_FILE = DATA_DIR / "ranking.json"
HISTORY_FILE = DATA_DIR / "history.json"

NOMES_CLAS = {
    "https://www.gamegol.com.br/2.0/_cla/external.asp?id=2765": "FÚRIA CEIFADORES",
    "https://www.gamegol.com.br/2.0/_cla/external.asp?id=228": "CEIFADORES FÚRIA",
    "https://www.gamegol.com.br/2.0/_cla/external.asp?id=3155": "FÚRIA JUNIORS",
    "https://www.gamegol.com.br/2.0/_cla/external.asp?id=2782": "NINJAS",
    "https://www.gamegol.com.br/2.0/_cla/external.asp?id=3099": "FÚRIA TALENT'S",
    "https://www.gamegol.com.br/2.0/_cla/external.asp?id=1115": "FÚRIA ACADEMY",
}

URLS_CLAS = list(NOMES_CLAS.keys())
MESES_PT = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}


def carregar_credenciais_google():
    raw = os.environ.get("GOOGLE_JSON_CREDENTIALS")
    if raw:
        return json.loads(raw)
    local = Path(__file__).resolve().parent / "tabelafrcf-6821c05e7550.json"
    if local.exists():
        with open(local, encoding="utf-8") as f:
            return json.load(f)
    raise RuntimeError("Credenciais Google não encontradas (env ou arquivo local).")


def extrair_id_time(link):
    match = re.search(r"id=(\d+)", link or "")
    return match.group(1) if match else link


def extrair_pontos(html_fonte):
    pts_ano = 0
    rank_mensal = 0

    m_p = re.search(r"Pontos Ano:.*?\(([\d\.]+)\)", html_fonte, re.S | re.I)
    if m_p:
        pts_ano = int(m_p.group(1).replace(".", ""))

    m_m = re.search(r"Geral Mensal:.*?\(([\d\.]+)\)", html_fonte, re.S | re.I)
    if m_m:
        rank_mensal = int(m_m.group(1).replace(".", ""))

    return pts_ano, rank_mensal


def extrair_historico_mensal(texto_visivel, html_fonte):
    """Tenta extrair pontos mensais do histórico visível na página do time."""
    historico = []
    ano_atual = datetime.now().year

    padroes = [
        r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[/\.\-](\d{2,4})\s*[:\-]?\s*([\d\.]+)",
        r"(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\s+(\d{4})\s*[:\-]?\s*([\d\.]+)",
    ]
    fonte = f"{texto_visivel}\n{html_fonte}"
    vistos = set()

    for padrao in padroes:
        for match in re.finditer(padrao, fonte, re.I):
            mes_txt = match.group(1).lower()
            ano_txt = match.group(2)
            pontos_txt = match.group(3).replace(".", "")
            mes_num = MESES_PT.get(mes_txt[:3])
            if not mes_num:
                continue
            ano = int(ano_txt)
            if ano < 100:
                ano += 2000
            chave = f"{ano}-{mes_num:02d}"
            if chave in vistos:
                continue
            vistos.add(chave)
            historico.append({
                "mes": chave,
                "pontos": int(pontos_txt),
            })

    historico.sort(key=lambda x: x["mes"])
    return historico


def extrair_titulos(texto_visivel, html_fonte):
    """Extrai títulos/troféus recentes da página do time."""
    titulos = []
    linhas = [l.strip() for l in texto_visivel.split("\n") if l.strip()]

    em_titulos = False
    for i, linha in enumerate(linhas):
        lower = linha.lower()
        if any(k in lower for k in ("título", "titulo", "troféu", "trofeu", "conquista")):
            em_titulos = True
            resto = re.sub(r"(títulos?|troféus?|conquistas?).*", "", linha, flags=re.I).strip()
            if resto and len(resto) > 3:
                titulos.append({"competicao": resto, "data": "", "temporada": ""})
            continue

        if em_titulos:
            if any(k in lower for k in ("estatística", "elenco", "histórico de", "pontos", "fundação")):
                em_titulos = False
                continue
            if len(linha) < 4 or linha.isdigit():
                continue

            data_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4}|\d{4})", linha)
            temporada_match = re.search(r"(temporada|temp\.?)\s*(\d{4})", linha, re.I)
            titulos.append({
                "competicao": linha,
                "data": data_match.group(1) if data_match else "",
                "temporada": temporada_match.group(2) if temporada_match else "",
            })

    for match in re.finditer(
        r"<a[^>]+href=[^>]*(?:campeonato|titulo|trofeu)[^>]*>([^<]+)</a>",
        html_fonte,
        re.I,
    ):
        nome = match.group(1).strip()
        if nome and len(nome) > 2:
            titulos.append({"competicao": nome, "data": "", "temporada": ""})

    unicos = []
    vistos = set()
    for t in titulos:
        chave = t["competicao"].lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(t)
    return unicos[:15]


def parse_time_page(texto_visivel, html_fonte, link):
    nome_time = "N/A"
    nome_do_cla_site = "SEM CLÃ"

    linhas = [l.strip() for l in texto_visivel.split("\n") if l.strip()]
    for i, linha in enumerate(linhas):
        if "Fundação:" in linha:
            nome_time = linha.split(" - ")[0].strip() if " - " in linha else (linhas[i - 1] if i > 0 else "N/A")
        if "Clã:" in linha:
            if len(linha.split("Clã:")) > 1:
                nome_do_cla_site = linha.split("Clã:")[1].strip()
            elif i + 1 < len(linhas):
                nome_do_cla_site = linhas[i + 1]

    if "Ver Clã" in nome_do_cla_site:
        nome_do_cla_site = nome_do_cla_site.replace("Ver Clã", "").strip()

    pts_ano, rank_mensal = extrair_pontos(html_fonte)
    historico_mensal = extrair_historico_mensal(texto_visivel, html_fonte)
    titulos = extrair_titulos(texto_visivel, html_fonte)

    return {
        "id": extrair_id_time(link),
        "nome": nome_time,
        "pontos_ano": pts_ano,
        "geral_mensal": rank_mensal,
        "cla": nome_do_cla_site,
        "link": link,
        "historico_mensal": historico_mensal,
        "titulos": titulos,
    }


def carregar_historico():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"snapshots": {}}


def salvar_snapshot_historico(historico, clas_dados):
    mes_chave = datetime.now().strftime("%Y-%m")
    snapshot = {"data_coleta": datetime.now(timezone.utc).isoformat(), "times": {}}

    for cla in clas_dados:
        for time_info in cla["times"]:
            team_id = time_info["id"]
            snapshot["times"][team_id] = {
                "nome": time_info["nome"],
                "cla": time_info["cla"],
                "cla_grupo": cla["nome"],
                "pontos_ano": time_info["pontos_ano"],
                "geral_mensal": time_info["geral_mensal"],
            }

    historico.setdefault("snapshots", {})[mes_chave] = snapshot
    return historico


def meses_ordenados(snapshots):
    return sorted(snapshots.keys())


def calcular_medias(historico, meses):
    snapshots = historico.get("snapshots", {})
    chaves = meses_ordenados(snapshots)[-meses:]
    if not chaves:
        return []

    acumulado = {}
    for chave in chaves:
        for team_id, info in snapshots[chave].get("times", {}).items():
            if team_id not in acumulado:
                acumulado[team_id] = {
                    "nome": info["nome"],
                    "cla": info["cla"],
                    "cla_grupo": info.get("cla_grupo", info["cla"]),
                    "soma": 0,
                    "contagem": 0,
                }
            acumulado[team_id]["soma"] += info.get("geral_mensal", 0)
            acumulado[team_id]["contagem"] += 1

    resultado = []
    for team_id, info in acumulado.items():
        if info["contagem"] == 0:
            continue
        media = round(info["soma"] / info["contagem"])
        resultado.append({
            "id": team_id,
            "nome": info["nome"],
            "cla": info["cla"],
            "cla_grupo": info["cla_grupo"],
            "media": media,
            "meses_considerados": info["contagem"],
        })

    resultado.sort(key=lambda x: x["media"], reverse=True)
    return resultado


def maior_pontuador_mensal(clas_dados):
    melhor = None
    for cla in clas_dados:
        for time_info in cla["times"]:
            if melhor is None or time_info["geral_mensal"] > melhor["geral_mensal"]:
                melhor = {
                    **time_info,
                    "cla_grupo": cla["nome"],
                }
    return melhor


def titulos_recentes(clas_dados, limite=30):
    todos = []
    for cla in clas_dados:
        for time_info in cla["times"]:
            for titulo in time_info.get("titulos", []):
                todos.append({
                    "time": time_info["nome"],
                    "cla": time_info["cla"],
                    "cla_grupo": cla["nome"],
                    "competicao": titulo.get("competicao", ""),
                    "data": titulo.get("data", ""),
                    "temporada": titulo.get("temporada", ""),
                    "link": time_info.get("link", ""),
                })
    return todos[:limite]


def montar_payload(clas_dados, historico):
    meses_disp = len(historico.get("snapshots", {}))
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mes_referencia": datetime.now().strftime("%Y-%m"),
        "clas": clas_dados,
        "stats": {
            "maior_pontuador_mensal": maior_pontuador_mensal(clas_dados),
            "media_3_meses": calcular_medias(historico, 3),
            "media_6_meses": calcular_medias(historico, 6),
            "meses_historico_disponiveis": meses_disp,
            "titulos_recentes": titulos_recentes(clas_dados),
        },
    }


def salvar_json(payload, historico):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RANKING_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def atualizar_planilha(planilha, clas_dados):
    planilha.clear()
    for indice, cla in enumerate(clas_dados):
        linha_inicial = (indice * 40) + 1
        nome_fixo_cla = cla["nome"]
        dados_cla = [
            [
                t["posicao"],
                t["nome"],
                t["pontos_ano"],
                t["geral_mensal"],
                t["cla"],
                "",
                "",
                "",
                t["link"],
            ]
            for t in cla["times"]
        ]
        if not dados_cla:
            continue
        cabecalho = [
            [nome_fixo_cla],
            ["Posição", "Nome", "Pontos Ano", "Geral Mensal", "Nome do Clã", "", "", "", "Link"],
        ]
        planilha.update(values=cabecalho + dados_cla, range_name=f"A{linha_inicial}")
        fim = linha_inicial + len(dados_cla) + 1
        planilha.format(
            f"A{linha_inicial}:I{fim}",
            {"horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE"},
        )
        planilha.format(
            f"A{linha_inicial}:I{linha_inicial + 1}",
            {"textFormat": {"bold": True}},
        )
import glob
import shutil

def gerenciar_limite_historico(pasta_historico="data/history"):
    """Mantém apenas os últimos 6 arquivos na pasta de histórico."""
    # Garante que a pasta existe
    if not os.path.exists(pasta_historico):
        os.makedirs(pasta_historico)
    
    # Lista arquivos .json, ordena por data de modificação
    arquivos = sorted(glob.glob(os.path.join(pasta_historico, "*.json")), key=os.path.getmtime)
    
    # Se passar de 6, remove os mais antigos
    while len(arquivos) > 6:
        os.remove(arquivos[0])
        print(f"🗑️ Histórico antigo removido: {arquivos[0]}")
        arquivos.pop(0)

def coletar_dados(driver, wait):
    clas_dados = []

    for indice, url_atual in enumerate(URLS_CLAS):
        nome_fixo_cla = NOMES_CLAS[url_atual]
        print(f"\n🔎 [{indice + 1}/{len(URLS_CLAS)}] Acessando Clã: {nome_fixo_cla}")
        driver.get(url_atual)
        time.sleep(5)

        vagas_ocupadas = 32
        try:
            texto_pagina = driver.find_element(By.TAG_NAME, "body").text
            match = re.search(r"Participantes\s+(\d+)/32", texto_pagina)
            if match:
                vagas_ocupadas = int(match.group(1))
        except Exception:
            pass

        elementos = driver.find_elements(By.CSS_SELECTOR, "a[href*='_team/external.asp?id=']")
        links_finais = []
        for el in elementos:
            href = el.get_attribute("href")
            if href and "destaque" not in href.lower() and href not in links_finais:
                links_finais.append(href)
        links_finais = links_finais[:vagas_ocupadas]

        times = []
        for pos, link in enumerate(links_finais, start=1):
            driver.get(link)
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                time.sleep(2)
                texto_visivel = driver.find_element(By.TAG_NAME, "body").text
                html_fonte = driver.page_source
                time_info = parse_time_page(texto_visivel, html_fonte, link)
                time_info["posicao"] = pos
                times.append(time_info)
                print(f"   > {time_info['nome']}: {time_info['pontos_ano']} pts | mensal {time_info['geral_mensal']}")
            except Exception as exc:
                print(f"   ⚠️ Erro ao ler time: {exc}")
                continue

        clas_dados.append({"nome": nome_fixo_cla, "url": url_atual, "times": times})

    return clas_dados


def main():
    if not SENHA:
        raise RuntimeError("Defina a variável de ambiente GAMEGOL_SENHA.")

    service_account_info = carregar_credenciais_google()
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
    client = gspread.authorize(creds)
    planilha = client.open(PLANILHA_NOME).sheet1

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 25)
def processar_historico_e_medias(clas_dados):
    try:
        print("🔐 Iniciando processo de login...")
        driver.get("https://www.gamegol.com.br")
        wait.until(EC.presence_of_element_located((By.ID, "iptUsuario"))).send_keys(LOGIN)
        driver.find_element(By.ID, "iptSenha").send_keys(SENHA + Keys.RETURN)
        time.sleep(10)
        print("✅ Login realizado com sucesso!")

        clas_dados = coletar_dados(driver, wait)

        historico = carregar_historico()
        historico = salvar_snapshot_historico(historico, clas_dados)
        # ... (dentro da sua função principal)
        
        # ... seu código atual que coleta e prepara os dados
        payload = montar_payload(clas_dados, historico)
        
        # Chamada para limpar históricos antigos e manter apenas 6
        gerenciar_limite_historico("data/history")
        
        salvar_json(payload, historico)
        print(f"\n💾 JSON salvo em {RANKING_FILE}")

        print("📤 Atualizando Google Sheets...")
        atualizar_planilha(planilha, clas_dados)
        print("\n🏆 PROCESSO FINALIZADO COM SUCESSO!")

    except Exception as e:
        print(f"\n❌ ERRO DURANTE A EXECUÇÃO: {e}")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
import glob

def gerenciar_limite_historico(pasta_historico="data/history"):
    """Mantém apenas os últimos 6 arquivos na pasta de histórico."""
    if not os.path.exists(pasta_historico):
        os.makedirs(pasta_historico)
    
    # Lista arquivos .json e ordena pelos mais antigos
    arquivos = sorted(glob.glob(os.path.join(pasta_historico, "*.json")), key=os.path.getmtime)
    
    # Se houver mais de 6, remove os mais antigos até sobrar apenas 6
    while len(arquivos) > 6:
        os.remove(arquivos[0])
        print(f"🗑️ Histórico antigo removido: {arquivos[0]}")
        arquivos.pop(0)