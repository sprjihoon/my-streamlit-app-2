import requests, json
r = requests.delete(
    'https://my-streamlit-app-2-production.up.railway.app/repair-log/barcodes',
    verify=False
)
print(r.status_code, r.json())
