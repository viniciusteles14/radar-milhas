# Teste sem internet: simula feeds e API e mostra as mensagens que iriam pro Telegram.
# Rode: python scripts/teste_offline.py  (depois apague docs/data/*.json)
import sys, random, json
import os; sys.path.insert(0, os.path.dirname(__file__)); os.chdir(os.path.join(os.path.dirname(__file__), ".."))
import promos, awards
from datetime import date, timedelta
rss = """<?xml version="1.0"?><rss><channel>
<item><title>Azul Fidelidade oferece 25% OFF no resgate de passagens</title><link>https://ex.com/1</link><description>&lt;p&gt;Desconto nacional&lt;/p&gt;</description><pubDate>Wed, 11 Nov 2026 10:00:00 +0000</pubDate></item>
<item><title>Alerta! Executiva da Azul para Lisboa a partir de 95 mil pontos</title><link>https://ex.com/2</link><description>Voos internacionais</description><pubDate>Wed, 11 Nov 2026 12:00:00 +0000</pubDate></item>
<item><title>Smiles com bônus de 100%</title><link>https://ex.com/3</link><description>x</description><pubDate>Wed, 11 Nov 2026 12:00:00 +0000</pubDate></item>
</channel></rss>""".encode()
items = promos.parse_feed(rss, "https://pontospravoar.com/feed/")
promos.run(items)          # primeira execução
items2 = items + promos.parse_feed(rss.replace(b"ex.com/2", b"ex.com/4").replace("Lisboa".encode(), "Orlando".encode()), "https://passageirodeprimeira.com/feed/")
promos.run(items2)         # segunda: 1 novo
# awards: simula API
def row(o,d,reg,dt,y,j):
    return {"Route":{"OriginAirport":o,"DestinationAirport":d,"DestinationRegion":reg},"Date":dt,
            "YAvailable":y is not None,"YMileageCost":str(y or 0),"JAvailable":j is not None,"JMileageCost":str(j or 0),"YDirect":True}
routes=[("VCP","LIS","Europe",70000,180000),("VCP","FLL","North America",50000,140000),("CNF","SSA","South America",9000,None),("EZE","MIA","North America",30000,None)]
H={}
for back in range(10,0,-1):
    day=(date.today()-timedelta(days=back)).isoformat()
    for o,d,reg,y,j in routes:
        H[f"{o}-{d}-economy"]=H.get(f"{o}-{d}-economy",[])+[{"day":day,"min":y+random.randint(-3000,3000),"flight_date":"2027-02-01"}]
        if j: H[f"{o}-{d}-business"]=H.get(f"{o}-{d}-business",[])+[{"day":day,"min":j+random.randint(-5000,5000),"flight_date":"2027-02-01"}]
json.dump(H,open("docs/data/history.json","w"))
rows=[row("VCP","LIS","Europe","2027-03-10",68000,120000), row("VCP","LIS","Europe","2027-03-11",72000,None),
      row("VCP","FLL","North America","2027-01-20",42000,145000), row("CNF","SSA","South America","2026-12-05",6500,None),
      row("EZE","MIA","North America","2027-01-01",10000,None)]
offers=[]
for r in rows: offers+=awards.normalize([r], awards.load_config()["awards"], "x")
awards.run(offers)
print("again (should dedupe):"); awards.run(offers)
