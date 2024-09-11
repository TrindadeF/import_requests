from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import pandas as pd
import time
import sys
import signal
import gspread
import os


load_dotenv()


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

def select_all_counties_except_first():
    try:
        for i, county in enumerate(county_options):
            if i == 0:
                continue
            county_select.select_by_value(county)
        print("Todos os condados, exceto o primeiro, foram selecionados.")
        search_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, 'doSearch'))
        )
        search_button.click()
    except UnexpectedAlertPresentException as alert_exception:
        alert = driver.switch_to.alert
        print(f"Alerta presente: {alert.text}")
        alert.accept()
        print("Alerta aceito. Continuando com o próximo condado.")
    except (TimeoutException, NoSuchElementException) as e:
        print(f"Erro ao tentar selecionar condados ou iniciar pesquisa: {e}")


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
        print(f"Erro ao encontrar botões de detalhes: {e}")


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

def salvar_em_google_sheets(data, nome_planilha, nome_aba):
    try:
        cliente = autenticar_google_sheets()  
        
        planilha = cliente.open(nome_planilha)
        
        try:
            aba = planilha.worksheet(nome_aba)
        except gspread.exceptions.WorksheetNotFound:
            aba = planilha.add_worksheet(title=nome_aba, rows="100", cols="20")
        
        if data:
            headers = list(data[0].keys())  
            valores = [list(item.values()) for item in data]  

            aba.clear()  
            aba.append_row(headers) 
            aba.append_rows(valores)  
            
            print(f"Dados enviados para a aba '{nome_aba}' na planilha '{nome_planilha}' com sucesso.")
    except Exception as e:
        print(f"Erro ao salvar dados no Google Sheets: {e}")

def stop_scrapping(signal, frame):
     print("\nInterrupção recebida! Salvando dados coletados...")
     salvar_em_google_sheets(data, ' Taxes Deed Research GoogleSheet ', "Mississípi")
     print("Dados salvos. Encerrando o script.")
     driver.quit()
     sys.exit()

signal.signal(signal.SIGINT, stop_scrapping)

select_all_counties_except_first()

scan_page()

while avancar_para_proxima_pagina():
    scan_page()

salvar_em_google_sheets(data, " Taxes Deed Research GoogleSheet ", "Mississípi")

driver.quit()