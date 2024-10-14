from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime
import pandas as pd
import time
import sys
import signal
import os
import gspread

options = webdriver.ChromeOptions()
options.add_argument("--disable-popup-blocking")
options.add_argument("--headless")  
options.add_argument("--blink-settings=imagesEnabled=false")  
driver = webdriver.Chrome(options=options)

driver.get("https://www.sos.ms.gov/tax-forfeited-inventory")

try:
    iframe = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, 'iframe'))
    )
    driver.switch_to.frame(iframe)
except (TimeoutException, NoSuchElementException) as e:
    print("Nenhum iframe encontrado ou erro ao trocar para o iframe:", e)
    driver.quit()
    raise

try:
    county_select_element = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.TAG_NAME, 'select'))
    )
except (TimeoutException, NoSuchElementException) as e:
    print(f"Erro ao localizar o campo 'county': {e}")
    driver.quit()
    raise

county_select = Select(county_select_element)
county_options = [option.get_attribute('value') for option in county_select.options if option.get_attribute('value')]

data = []
unique_records = set()  

def extrair_detalhes_parcel(soup):
    detalhes = {}
    try:
        container_div = soup.find('div', class_='dContainer')
        if container_div:
            rows = container_div.find_all('div', class_='dRow')
            
            rows = rows[2:13] 

            for row in rows:
                divs = row.find_all(['div'], class_=['dCell', 'dCellGrowable'])
                
                for i in range(0, len(divs), 2):
                    if i + 1 < len(divs):  
                        chave = divs[i].get_text(separator=' ', strip=True)
                        valor = divs[i + 1].get_text(separator=' ', strip=True)

                        if not chave:
                            chave = 'Adress Continue'
                        if not valor:
                            valor = 'N/A'
                        
                        if chave and valor:
                            detalhes[chave] = valor
    except Exception as e:
        print(f"Erro ao extrair detalhes: {e}")
    return detalhes


def coletar_dados():
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'dContainer'))
        )
        time.sleep(3)
        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')
        detalhes = extrair_detalhes_parcel(soup)
        if detalhes:
            detalhes_tuple = tuple(sorted(detalhes.items()))
            if detalhes_tuple not in unique_records:
                unique_records.add(detalhes_tuple)  
                data.append(detalhes)  
        print("Detalhes coletados:", detalhes)
    except (TimeoutException, NoSuchElementException) as e:
        print(f"Erro ao coletar dados: {e}")

selected_county = None  

def select_county_by_user_input():
    global selected_county 
    try:
        print("Lista de condados disponíveis:")
        for i, county in enumerate(county_options):
            print(f"{i+1}: {county}")

        county_input = input("Digite o número do condado que deseja selecionar: ")

        try:
            county_index = int(county_input) - 1  
            if 0 <= county_index < len(county_options):
                county_select.select_by_value(county_options[county_index])
                selected_county = county_options[county_index]  
                print(f"Condado '{selected_county}' selecionado com sucesso.")
            else:
                print("Número inválido. Selecione um número da lista.")
                return False
        except ValueError:
            print("Entrada inválida. Digite um número.")
            return False

        search_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, 'doSearch'))
        )
        search_button.click()

    except UnexpectedAlertPresentException as alert_exception:
        alert = driver.switch_to.alert
        print(f"Alerta presente: {alert.text}")
        alert.accept()
        print("Alerta aceito. Continuando com a seleção do condado.")
    except (TimeoutException, NoSuchElementException) as e:
        print(f"Erro ao tentar selecionar o condado ou iniciar a pesquisa: {e}")
        return False

    return True  

def scan_page():
    try:
        details_buttons = WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.ID, 'getDetail'))
        )
        for index, details_button in enumerate(details_buttons):
            driver.execute_script("arguments[0].scrollIntoView(true);", details_button)
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable(details_button))
            try:
                print(f"Processando o item {index + 1} de {len(details_buttons)}")
                details_button.click()
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, 'dContainer'))
                )
                time.sleep(3)
                coletar_dados()
                back_button = WebDriverWait(driver, 20).until(
                    EC.element_to_be_clickable((By.ID, 'Button2'))
                )
                back_button.click()
                WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located((By.ID, 'getDetail'))
                )
            except (TimeoutException, NoSuchElementException) as e:
                print(f"Erro ao tentar coletar dados ou retornar no item {index + 1}: {e}")
                continue
    except TimeoutException as e:
        print(f"Este condado não possui itens para ser coletados !")


def avancar_para_proxima_pagina():
    try:
        next_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(text(), 'Next >>')]"))
        )
        if next_button.is_displayed():
            next_button.click()
            print("Avançando para a próxima página...")
            time.sleep(6)
            scan_page()
        else:
            print("Botão 'Next >>' está desabilitado, fim da paginação.")
            return False
    except TimeoutException:
        print("Botão 'Next >>' não encontrado, fim da paginação.")
        return False
    
def autenticar_google_sheets():
    try:
        credentials_info = {
            "type": os.getenv("GOOGLE_TYPE"),
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),  
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
            "universe_domain": os.getenv("GOOGLE_UNIVERSE_DOMAIN")
        }

        SCOPES = ['https://www.googleapis.com/auth/spreadsheets',
                  "https://www.googleapis.com/auth/drive"]

        credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        cliente = gspread.authorize(credentials)
        return cliente  
    except Exception as e:
        print(f"Erro ao autenticar no Google Sheets: {e}")
        return None


def buscar_planilha_por_nome(drive_service, condado):
    query = f"mimeType='application/vnd.google-apps.spreadsheet' and name='{condado}' and trashed=false"
    results = drive_service.files().list(q=query, spaces='drive', fields="files(id, name)").execute()
    items = results.get('files', [])
    
    if not items:
        print(f"Nenhuma planilha encontrada para o condado '{condado}'")
        return None
    else:
        print(f"Planilha '{items[0]['name']}' encontrada.")
        return items[0]['id']  

def salvar_em_google_sheets(data, nome_planilha, nome_aba):
    try:
        cliente = autenticar_google_sheets()  
        if cliente is None:
            print("Falha ao autenticar no Google Sheets. Não é possível salvar os dados.")
            return
        
        try:
            pasta_projeto = cliente.open(nome_planilha.strip())  
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"Planilha '{nome_planilha}' não encontrada.")
            return

        try:
            aba = pasta_projeto.worksheet(nome_aba.strip())  
            print(f"Aba '{nome_aba}' já existe. Atualizando dados...")
        except gspread.exceptions.WorksheetNotFound:
            aba = pasta_projeto.add_worksheet(title=nome_aba.strip(), rows="100", cols="20")
            print(f"Aba '{nome_aba}' criada com sucesso.")

        if data:
            headers = list(data[0].keys())  
            valores = [list(item.values()) for item in data] 

            existing_data = aba.get_all_values()  
       
            if len(existing_data) == 0:
                aba.append_row(headers) 
            else:
                range_name = 'A1:' + chr(64 + len(headers)) + '1'
                aba.update(range_name=range_name, values=[headers])  
                
            aba.append_rows(valores)  
            print(f"Dados adicionados na aba '{nome_aba}'.")
        else:
            print("Nenhum dado a ser salvo.")
    except Exception as e:
        print(f"Erro ao salvar dados no Google Sheets: {e}")

def stop_scrapping(signal, frame, data, condado):
    try:
        print("\nInterrupção recebida! Salvando dados coletados...")

        salvar_em_google_sheets(data, condado, condado)
        
        print(f"Dados salvos para o condado {condado}. Encerrando o script.")
    except Exception as e:
        print(f"Erro ao salvar os dados: {str(e)}")
    finally:
        driver.quit()
        sys.exit()

if not select_county_by_user_input():
    print("Seleção de condado falhou. Encerrando o script.")
    sys.exit(1)  

print(f"Condado selecionado: {selected_county}") 

signal.signal(signal.SIGINT, lambda s, f: stop_scrapping(s, f, data, selected_county))

scan_page()

while avancar_para_proxima_pagina():
    scan_page()

salvar_em_google_sheets(data, selected_county, "Dados_Atualizados")  




