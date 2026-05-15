import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"
slug = "el-tutorial-es-demasiado-dificil"
cap_url = f"https://nartag.com/manga/{slug}/capitulos/capitulo-1/"

html = scraper.get(cap_url, headers={"User-Agent": UA}, timeout=30).text
soup = BeautifulSoup(html, 'html.parser')
form = soup.find('form', id='rk_madara_redirect')

fields = {
    inp['name']: inp.get('value', '')
    for inp in form.find_all('input', {'type': 'hidden'})
}
action = form.get('action')
print("Fields:", fields)
print("Action:", action)

# Hacer el POST
resp = scraper.post(
    action,
    data=fields,
    headers={
        "User-Agent": UA,
        "Referer": cap_url,
        "Origin": "https://nartag.com",
        "Content-Type": "application/x-www-form-urlencoded",
    },
    timeout=30,
    allow_redirects=True,
)
print("\nStatus:", resp.status_code)
print("URL final:", resp.url)

# Ver qué imágenes hay en el HTML resultante
soup2 = BeautifulSoup(resp.text, 'html.parser')
imgs = soup2.find_all('img')
print(f"\nTotal <img>: {len(imgs)}")
for i, img in enumerate(imgs):
    src = img.get('src') or img.get('data-src') or ''
    print(f"  [{i}] {src}")