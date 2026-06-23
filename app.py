import asyncio
import json
import re
import requests
import aiohttp
import pandas as pd
import streamlit as st
import sqlite3

DB_FILE = "ragnarok.db"

USUARIOS = [
    "ranos",
    "jofrey",
    "mono"
]

def get_conn():
    return sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )
    
def criar_banco():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS listas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL,
            nome TEXT NOT NULL,
            UNIQUE(usuario, nome)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS lista_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lista_id INTEGER NOT NULL,
            nome_item TEXT NOT NULL,
            FOREIGN KEY(lista_id)
                REFERENCES listas(id)
        )
    """)
    conn.commit()
    conn.close()

def salvar_lista(usuario,nome_lista,itens):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM listas
        WHERE usuario = ?
        AND nome = ?
        """,
        (
            usuario,
            nome_lista
        )
    )
    row = cur.fetchone()
    if row:
        lista_id = row[0]
        cur.execute(
            """
            DELETE FROM lista_itens
            WHERE lista_id = ?
            """,
            (
                lista_id,
            )
        )
    else:
        cur.execute(
            """
            INSERT INTO listas
            (
                usuario,
                nome
            )
            VALUES (?, ?)
            """,
            (
                usuario,
                nome_lista
            )
        )
        lista_id = cur.lastrowid
    for item in itens:
        cur.execute(
            """
            INSERT INTO lista_itens
            (
                lista_id,
                nome_item
            )
            VALUES (?, ?)
            """,
            (
                lista_id,
                item
            )
        )
    conn.commit()
    conn.close()

def listar_listas(usuario):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            nome
        FROM listas
        WHERE usuario = ?
        ORDER BY nome
        """,
        (
            usuario,
        )
    )
    dados = cur.fetchall()
    conn.close()
    return dados

def buscar_nome_lista_selecionada(lista_escolhida):
    if lista_escolhida:
        return lista_escolhida
    return ""

def carregar_itens_lista(lista_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT nome_item
        FROM lista_itens
        WHERE lista_id = ?
        ORDER BY nome_item
        """,
        (
            lista_id,
        )
    )
    dados = cur.fetchall()
    conn.close()
    return "\n".join(
        [
            x[0]
            for x in dados
        ]
    )

def excluir_lista(usuario,nome_lista):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
        FROM listas
        WHERE usuario = ?
        AND nome = ?
        """,
        (
            usuario,
            nome_lista
        )
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    lista_id = row[0]
    cur.execute(
        """
        DELETE FROM lista_itens
        WHERE lista_id = ?
        """,
        (
            lista_id,
        )
    )
    cur.execute(
        """
        DELETE FROM listas
        WHERE id = ?
        """,
        (
            lista_id,
        )
    )
    conn.commit()
    conn.close()

def extrair_dados_items_do_html(response_text, search_word):
    try:
        partes = re.findall(
            r'self\.__next_f\.push\(\[1,"(.*?)"\]\)',
            response_text,
            flags=re.DOTALL
        )
        if partes:
            conteudo = "".join(partes)

            try:
                conteudo = bytes(
                    conteudo,
                    "utf-8"
                ).decode(
                    "unicode_escape"
                )
            except Exception:
                pass
        else:
            conteudo = response_text
        match = re.search(
            r'"queryParams":\{.*?\},"list":(\[.*?\]),"totalCount":(\d+)',
            conteudo,
            flags=re.DOTALL
        )
        if not match:
            match = re.search(
                r'\\"queryParams\\":\{.*?\},\\"list\\":(\[.*?\]),\\"totalCount\\":(\d+)',
                response_text,
                flags=re.DOTALL
            )
            if not match:
                print(f"NÃO ACHOU DADOS PARA {search_word}")
                return []

            lista_json = match.group(1)

            lista_json = bytes(
                lista_json,
                "utf-8"
            ).decode(
                "unicode_escape"
            )
        else:
            lista_json = match.group(1)
        items = json.loads(lista_json)
        print(
            f"{search_word}: {len(items)} itens encontrados"
        )
        return items
    except Exception as ex:
        print(
            f"Erro parseando {search_word}: {ex}"
        )
        try:
            print(
                "Trecho do JSON:",
                lista_json[:500]
            )
        except:
            pass
        return []

async def buscar_items_ragnarok_async(
    session,
    search_word,
    store_type="BUY",
    server_type="FREYA",
    sort_type="LOW_PRICE",
    limit=5
):
    url = "https://ro.gnjoylatam.com/pt/intro/shop-search/trading"
    params = {
        "storeType": store_type,
        "serverType": server_type,
        "searchWord": search_word,
        "sortType": sort_type
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://ro.gnjoylatam.com/",
        "Origin": "https://ro.gnjoylatam.com"
    }
    try:
        async with session.get(
            url,
            params=params,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status != 200:
                print(
                    f"Erro {response.status} para {search_word}"
                )
                return []
            response_text = await response.text()
            items_raw = extrair_dados_items_do_html(
                response_text,
                search_word
            )
            if not items_raw:
                return []
            itens_filtrados = items_raw[:limit]
            resultados = []
            for item in items_raw[:limit]:
                detalhes = await buscar_detalhes_item(
                    session=session,
                    search_word=search_word,
                    svr_id=item["svrId"],
                    map_id=item["mapId"],
                    ssi=item["ssi"]
                )
                resultados.append({
                    "Pesquisa": search_word,
                    "Item": detalhes.get("itemFullName"),
                    "Preço": item.get("itemPrice"),
                    "Quantidade": item.get("itemCnt"),
                    "Loja": item.get("storeName"),
                    "Vendedor": item.get("itemSellerCharName"),
                    "Mapa": detalhes.get("mapName"),
                    "X": detalhes.get("xpos"),
                    "Y": detalhes.get("ypos"),
                    "Imagem": detalhes.get("databaseImgPath"),
                    "ItemId": detalhes.get("itemId"),
                })
            return resultados
    except Exception as e:
        print(
            f"Erro em {search_word}: {e}"
        )
        return []

async def consultar_itens(lista_itens, limite):
    async with aiohttp.ClientSession() as session:
        tasks = [
            buscar_items_ragnarok_async(
                session=session,
                search_word=item,
                limit=limite
            )
            for item in lista_itens
        ]
        resultados = await asyncio.gather(*tasks)
    final = []
    for grupo in resultados:
        final.extend(grupo)
    return final

def extrair_detalhes_post(response_text):
    try:
        match = re.search(
            r'1:(\{"data":.*?"success":true\})',
            response_text,
            re.DOTALL
        )
        if not match:
            return {}
        json_str = match.group(1)
        detalhe = json.loads(json_str)
        return detalhe.get("data", {})
    except Exception as e:
        print("Erro parseando detalhe:", e)
        return {}

async def buscar_detalhes_item(
    session,
    search_word,
    svr_id,
    map_id,
    ssi
):
    url = (
        "https://ro.gnjoylatam.com/pt/intro/shop-search/trading"
        f"?storeType=BUY"
        f"&serverType=FREYA"
        f"&searchWord={search_word}"
        f"&sortType=LOW_PRICE"
    )
    headers = {
        "Accept": "text/x-component",
        "Content-Type": "text/plain;charset=UTF-8",
        "Next-Action": "403371b38682ba2dd997d1b755ba1bb20fadfa07a9",
        "Origin": "https://ro.gnjoylatam.com",
        "Referer": url,
        "User-Agent": "Mozilla/5.0"
    }
    payload = [
        {
            "type": "store",
            "params": {
                "svrId": svr_id,
                "mapId": map_id,
                "ssi": ssi
            }
        }
    ]
    try:
        async with session.post(
            url,
            headers=headers,
            json=payload
        ) as response:
            texto = await response.text()
            detalhe = extrair_detalhes_post(texto)            
            return detalhe
    except Exception as e:
        print(
            f"Erro detalhes {ssi}: {e}"
        )
        return {}

def limpar_descricao_rag(texto):
    if not texto:
        return ""
    texto = re.sub(r"\^[0-9A-Fa-f]{6}", "", texto)
    return texto

criar_banco()

st.set_page_config(
    page_title="Ragnarok Search",
    layout="wide"
)
st.title("Ragnarok Market Search")
col_esq, col_dir = st.columns(
    [3, 1]
)
with col_esq:
    usuario = st.selectbox(
        "Usuário",
        USUARIOS
    )
    listas = listar_listas(
        usuario
    )
    mapa_listas = {
        nome: lista_id
        for lista_id, nome in listas
    }
    lista_escolhida = st.selectbox(
        "Lista Salva",
        [""] + list(mapa_listas.keys())
    )
    texto_lista = ""
    if lista_escolhida:
        texto_lista = carregar_itens_lista(
            mapa_listas[
                lista_escolhida
            ]
        )
    itens = st.text_area(
        "Itens (1 por linha)",
        value=texto_lista,
        height=200
    )
    limite = st.number_input(
        "Quantidade de resultados",
        min_value=1,
        max_value=20,
        value=5
    )
with col_dir:
    with st.container(border=True):
        st.subheader(
            "Gerenciar Listas"
        )
        st.subheader("Salvar nova lista")
        nome_padrao = ""
        if lista_escolhida:
            nome_padrao = lista_escolhida
        nome_lista = st.text_input(
            "Nome da Lista",
            value=nome_padrao
        )
        if st.button(f':{'green'}[Upsert lista]'):
            if not nome_lista.strip():
                st.error("Informe um nome para a lista.")
            else:
                lista_itens = [
                    x.strip()
                    for x in itens.splitlines()
                    if x.strip()
                ]
                salvar_lista(
                    usuario,
                    nome_lista.strip(),
                    lista_itens
                )
                st.success("Lista salva com sucesso." )
                st.rerun()
        if lista_escolhida:
            if st.button(f':{'red'}[Excluir lista]'):
                excluir_lista(
                    usuario,
                    lista_escolhida
                )
                st.success(
                    "Lista removida"
                )
                st.rerun()
st.divider()
if st.button("Pesquisar"):
    lista_itens = [
        x.strip()
        for x in itens.splitlines()
        if x.strip()
    ]
    with st.spinner("Consultando Ragnarok..."):
        resultados = asyncio.run(
            consultar_itens(
                lista_itens,
                limite
            )
        )
    if resultados:
        df = pd.DataFrame(resultados)
        st.success(
            f"{len(df)} registros encontrados"
        )
        df = df.sort_values(
            ["Pesquisa", "Preço"]
        )
        for item_pesquisado in lista_itens:
            df_item = df[
                df["Pesquisa"].str.lower()
                == item_pesquisado.lower()
            ]
            if len(df_item) == 0:
                continue
            st.subheader(f"📦 {item_pesquisado}")
            df_exibicao = df_item.copy()
            df_exibicao["Detalhes"] = df_exibicao["ItemId"].apply(
                lambda item_id: f"https://www.divine-pride.net/database/item/{item_id}".replace(".0", "")
            )
            df_exibicao["Preço"] = df_exibicao["Preço"].apply(
              lambda v: f"{int(v):,}".replace(",", ".") if pd.notna(v) else ""
            )
            st.data_editor(
                df_exibicao[
                    [
                        "Imagem",
                        "Item",
                        "Preço",
                        "Quantidade",
                        "Loja",
                        "Vendedor",
                        "Mapa",
                        "X",
                        "Y",
                        "Detalhes",
                    ]
                ],
                column_config={
                    "Imagem": st.column_config.ImageColumn(
                        "Imagem",
                        help="Imagem do item",
                        width="small"
                    ),
                    "Detalhes": st.column_config.LinkColumn(
                        "Detalhes",
                        display_text="🔎 divinepride"
                    )
                },
                hide_index=True,
                width="stretch"
            )
