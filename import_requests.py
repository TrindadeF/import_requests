from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoSuchElementException
from bs4 import BeautifulSoup
import pandas as pd
import time


options = webdriver.ChromeOptions()
options.add_argument("--disable-popup-blocking")
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

def extrair_detalhes_parcel(soup):
    try:
        detalhes = []
        
        container_div = soup.find('div', class_='dContainer')
        
        if container_div:
            
            divs = container_div.find_all('div', limit=60)  
            for div in divs:
                detalhes.append(div.get_text(separator='\n', strip=True).split('\n'))
        else:
            print("Não encontrou a div com a classe 'dContainer'.")
        
        return detalhes
    except Exception as e:
        print(f"Erro ao extrair detalhes: {e}")
        return []


def coletar_dados():
    
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'dContainer'))
        )
        time.sleep(2)

        page_html = driver.page_source
        
        with open("pagina_debug.html", "w", encoding="utf-8") as file:
            file.write(page_html)

        soup = BeautifulSoup(page_html, 'html.parser')

        detalhes = extrair_detalhes_parcel(soup)
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

        # Espera que o botão de pesquisa fique clicável e clica nele
        search_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.ID, 'doSearch'))
        )
        search_button.click()

        # Espera os botões "Show Details" aparecerem
        details_buttons = WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.ID, 'getDetail'))
        )

        
        for index, details_button in enumerate(details_buttons):
            try:
                print(f"Processando o item {index + 1} de {len(details_buttons)}")
                details_button.click()
                time.sleep(2)  

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



select_all_counties_except_first()

df = pd.DataFrame(data)
df.to_csv('tax_forfeited_inventory_detalhes.csv', index=False)


driver.quit()
