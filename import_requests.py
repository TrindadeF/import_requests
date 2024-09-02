from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoSuchElementException
from bs4 import BeautifulSoup
import pandas as pd
import time

# Configurações do Selenium
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
except Exception as e:
    print("Nenhum iframe encontrado ou erro ao trocar para o iframe:", e)

try:
    county_select_element = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.TAG_NAME, 'select'))
    )
except Exception as e:
    print(f"Erro ao localizar o campo 'county': {e}")
    driver.quit()
    raise

county_select = Select(county_select_element)
county_options = [option.get_attribute('value') for option in county_select.options if option.get_attribute('value')]

data = []
unique_records = set()  

def extrair_detalhes_parcel(soup):
    try:
        detalhes = {}
        container_div = soup.find('div', class_='dContainer')

        if container_div:
            # Encontrar todas as divs que contêm o texto
            divs = container_div.find_all('div', limit=60)  
            current_key = None

            for div in divs:
                text = div.get_text(separator='\n', strip=True)
                print("Texto encontrado:", text)  # Log para verificar o que está sendo encontrado

                # Ajuste de extração para capturar pares chave-valor
                if ':' in text:
                    parts = text.split(':', 1)
                    key = parts[0].strip()
                    value = parts[1].strip() if len(parts) > 1 else ''
                    current_key = key if value else current_key  # Define chave corrente se não houver valor imediato
                    detalhes[current_key] = value if value else detalhes.get(current_key, '')
                elif current_key:
                    # Caso onde o valor está em uma linha separada, mas temos uma chave corrente
                    detalhes[current_key] += f' {text}' if detalhes[current_key] else text

        else:
            print("Não encontrou a div com a classe 'dContainer'.")
            # Log para depuração, mostrando o HTML completo da página
            print(soup.prettify())  

        return detalhes
    except Exception as e:
        print(f"Erro ao extrair detalhes: {e}")
        return {}

def coletar_dados():
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'dContainer'))
        )
        time.sleep(3)  # Aumente o tempo de espera se necessário

        page_html = driver.page_source
        soup = BeautifulSoup(page_html, 'html.parser')
        detalhes = extrair_detalhes_parcel(soup)
        
        if any(detalhes.values()):  # Check if at least one value is not empty
            detalhes_tuple = tuple(sorted(detalhes.items()))

            if detalhes_tuple not in unique_records:
                unique_records.add(detalhes_tuple)  
                data.append(detalhes)  
        
        print("Detalhes coletados:", detalhes)

    except (TimeoutException, NoSuchElementException) as e:
        print(f"Erro ao coletar dados: {e}")
    except Exception as e:
        print(f"Erro inesperado ao processar a página: {e}")

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

        details_buttons = WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.ID, 'getDetail'))
        )

        for index, details_button in enumerate(details_buttons):
            try:
                print(f"Processando o item {index + 1} de {len(details_buttons)}")
                details_button.click()
                time.sleep(3)  # Pode ajustar o tempo conforme necessário

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

    except UnexpectedAlertPresentException as alert_exception:
        alert = driver.switch_to.alert
        print(f"Alerta presente: {alert.text}")
        alert.accept()
        print("Alerta aceito. Continuando com o próximo condado.")
    except (TimeoutException, NoSuchElementException) as e:
        print(f"Erro ao tentar selecionar condados ou iniciar pesquisa: {e}")

def salvar_como_csv(data, nome_arquivo):
    if data:
        df = pd.DataFrame(data)  # Converte a lista de dicionários em um DataFrame do pandas
        df.to_csv(nome_arquivo, index=False)  # Salva o DataFrame como um arquivo CSV
        print(f"Dados salvos em {nome_arquivo}")

# Executa a função para coletar dados
select_all_counties_except_first()

# Salva os dados coletados em um arquivo CSV
salvar_como_csv(data, 'dados_coletados.csv')

# Fecha o navegador
driver.quit()
