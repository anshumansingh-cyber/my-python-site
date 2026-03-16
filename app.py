import os
import pandas as pd
from flask import Flask, render_template, request
from deep_translator import GoogleTranslator
from flask_caching import Cache

app = Flask(__name__)

# CHANGED: Using 'SimpleCache' for Render. 
# FileSystemCache often fails on free cloud hosts without persistent disks.
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 604800})

def search_excel(user_input):
    try:
        excel_data = pd.read_excel('database.xlsx', sheet_name=None)
        for sheet in excel_data:
            excel_data[sheet].columns = excel_data[sheet].columns.astype(str).str.strip().str.lower()

        df_names = excel_data['crop_name']
        # Search in the second column (index 1) which usually contains names
        match = df_names[df_names.iloc[:, 1].str.contains(user_input, case=False, na=False)]
        
        if match.empty: return None

        crop_row = match.iloc[0]
        crop_id = crop_row.iloc[0] # Assuming first column is the ID
        
        def get_sheet_info(sheet_key, cid):
            if sheet_key not in excel_data: return {"rows": [], "columns": []}
            df = excel_data[sheet_key]
            filtered_df = df[df.iloc[:, 1] == cid].copy() # Filter by crop_id column
            display_cols = filtered_df.columns.tolist()[2:]
            return {
                "rows": filtered_df.to_dict('records'),
                "columns": display_cols
            }

        return {
            "name": str(crop_row.iloc[1]),
            "image": crop_row.get('image_file', None),
            "requirements": get_sheet_info('crop_requirement', crop_id),
            "steps": get_sheet_info('cultivation_step', crop_id),
            "risks": get_sheet_info('risk_associated', crop_id)
        }
    except Exception as e:
        print(f"Excel Error: {e}")
        return None

@cache.memoize()
def get_translated_crop_data(crop_name, target_lang):
    data = search_excel(crop_name)
    if not data or target_lang == 'en':
        return data

    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        # Prepare list for batch translation
        to_translate = [data['name']]
        sections = ['requirements', 'steps', 'risks']

        for s in sections:
            cols = data[s]['columns']
            to_translate.extend([str(c) for c in cols])
            for row in data[s]['rows']:
                for col_name in cols:
                    val = row.get(col_name, "")
                    to_translate.append(str(val) if pd.notnull(val) else "")

        translated_list = translator.translate_batch(to_translate)

        # Map translations back
        cursor = 0
        data['name'] = translated_list[cursor]
        cursor += 1

        for s in sections:
            old_cols = data[s]['columns']
            new_cols = []
            for _ in old_cols:
                new_cols.append(translated_list[cursor])
                cursor += 1
            
            new_rows = []
            for _ in data[s]['rows']:
                new_row = {}
                for i in range(len(new_cols)):
                    new_row[new_cols[i]] = translated_list[cursor]
                    cursor += 1
                new_rows.append(new_row)
            
            data[s]['columns'] = new_cols
            data[s]['rows'] = new_rows
        
        return data
    except Exception as e:
        print(f"Translation Error: {e}")
        return data

@app.route('/')
def home():
    try:
        df = pd.read_excel('database.xlsx', sheet_name='crop_name')
        crops = df.iloc[:, 1].dropna().unique().tolist()
    except Exception as e:
        print(f"Home Error: {e}")
        crops = []
    return render_template('index.html', crops=crops)

@app.route('/get_crop', methods=['POST'])
def get_crop():
    user_search = request.form.get('search_box')
    target_lang = request.form.get('language', 'en')
    result = get_translated_crop_data(user_search, target_lang)
    if result:
        # Fixed: your template call was 'results.html' but most Flask apps use 'result.html'
        # Change this to match your actual filename in the templates folder
        return render_template('result.html', data=result)
    return "Crop not found!"

if __name__ == '__main__':
    # Bind to PORT provided by Render or default to 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

