import json, os, base64

path = 'LTE_RCA_Incidents_Based.ipynb'
outdir = 'photos'
os.makedirs(outdir, exist_ok=True)
count = 0

with open(path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

for cell_i, cell in enumerate(nb.get('cells', []), start=1):
    if cell.get('cell_type') != 'code':
        continue
    for out_i, out in enumerate(cell.get('outputs', []), start=1):
        png = None
        if isinstance(out, dict):
            data = out.get('data')
            if isinstance(data, dict):
                png = data.get('image/png')
        if png:
            if isinstance(png, list):
                png = ''.join(png)
            dest = os.path.join(outdir, f'notebook_cell{cell_i:03d}_output{out_i:02d}.png')
            with open(dest, 'wb') as wf:
                wf.write(base64.b64decode(png))
            print(dest)
            count += 1
            continue
        attachments = cell.get('attachments', {})
        if isinstance(attachments, dict):
            for att_name, att in attachments.items():
                if isinstance(att, dict) and 'image/png' in att:
                    data = att['image/png']
                    if isinstance(data, list):
                        data = ''.join(data)
                    dest = os.path.join(outdir, f'cell{cell_i:03d}_{att_name}')
                    with open(dest, 'wb') as wf:
                        wf.write(base64.b64decode(data))
                    print(dest)
                    count += 1

print('TOTAL', count)
