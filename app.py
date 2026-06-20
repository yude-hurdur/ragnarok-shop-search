import asyncio
import json
import re
import requests
import aiohttp
import pandas as pd
import streamlit as st

import json
import re

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

@st.cache_data(ttl=86400)
def buscar_item_ragnaplace(item_id):
    try:
        url = (
            f"https://api.ragnaplace.com/api/db/item/"
            f"{item_id}?gateway=laro-pt"
        )

        response = requests.get(
            url,
            timeout=10
        )

        if response.status_code != 200:
            return None

        return response.json()["data"]

    except Exception as e:
        print(e)
        return None

st.set_page_config(
    page_title="Ragnarok Search",
    layout="wide"
)
st.title("Ragnarok Market Search")
itens = st.text_area(
    "Itens (1 por linha)",
    value="Morango\nRosário Dourado",
    height=200
)
limite = st.number_input(
    "Quantidade de resultados",
    min_value=1,
    max_value=20,
    value=5
)

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
        print(df)
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
            st.data_editor(
                df_item[
                    [
                        "Imagem",
                        "Item",
                        "Preço",
                        "Quantidade",
                        "Loja",
                        "Vendedor",
                        "Mapa",
                        "X",
                        "Y"
                    ]
                ],
                column_config={
                    "Imagem": st.column_config.ImageColumn(
                        "Imagem",
                        help="Imagem do item",
                        width="small"
                    )
                },
                hide_index=True,
                width="stretch"
            )   
            item_escolhido = st.selectbox(
                f"🔍 Ver descrição ({item_pesquisado})",
                df_item["Item"].tolist(),
                key=f"desc_{item_pesquisado}"
            )
            registro = df_item[
                df_item["Item"] == item_escolhido
            ].iloc[0]
            dados_item = buscar_item_ragnaplace(
                registro["ItemId"]
            )
            if dados_item:
                descricao = limpar_descricao_rag(
                    dados_item.get(
                        "identifiedDescriptionName",
                        "Sem descrição"
                    )
                )

                col1, col2 = st.columns([1, 3])

                with col1:
                    st.image(
                        registro["Imagem"],
                        width=180
                    )

                with col2:
                    st.markdown(
                        f"### {dados_item['identifiedDisplayName']}"
                    )

                st.text(descricao)           
            else:
                st.warning(
                    "Nenhum resultado encontrado"
                )
