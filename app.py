import os
import pandas as pd
from flask import Flask, render_template, request
from deep_translator import GoogleTranslator
from flask_caching import Cache

app = Flask(__name__)

# FileSystem Cache saves translations to a folder so they survive restarts
cache = Cache(app, config={
    'CACHE_TYPE': 'FileSystemCache',
    'CACHE_DIR': 'flask_cache',
    'CACHE_DEFAULT_TIMEOUT': 604800  # 1 week
})

def search_excel(user_input):
    """Retrieves raw crop data from the Excel database."""
    try:
        excel_data = pd.read_excel('database.xlsx', sheet_name=None)
        # Standardize column headers
        for sheet in excel_data:
            excel_data[sheet].columns = excel_data[sheet].columns.astype(str).str.strip().str.lower()

        df_names = excel_data['crop_name']
        match = df_names[df_names['crop_name'].str.contains(user_input, case=False, na=False)]
        
        if match.empty: return None

        crop_row = match.iloc[0] # Corrected iloc access
        crop_id = crop_row['crop_id']
        
        def get_sheet_info(sheet_key, cid):
            if sheet_key not in excel_data: return {"rows": [], "columns": []}
            df = excel_data[sheet_key]
            # Filter rows by Crop ID
            filtered_df = df[df['crop_id'] == cid].copy()
            # Remove the first two columns (usually id/crop_id) for display
            display_cols = filtered_df.columns.tolist()[2:]
            return {
                "rows": filtered_df.to_dict('records'),
                "columns": display_cols
            }

        return {
            "name": str(crop_row['crop_name']),
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
    """Collects all text, translates it, and rebuilds the data structure."""
    data = search_excel(crop_name)
    if not data or target_lang == 'en':
        return data

    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        to_translate = [data['name']]
        sections = ['requirements', 'steps', 'risks']

        # 1. Collect all headers and row values in strict order
        for s in sections:
            cols = data[s]['columns']
            to_translate.extend([str(c) for c in cols]) # Headers
            for row in data[s]['rows']:
                for col_name in cols: # Cell values
                    val = row.get(col_name, "")
                    to_translate.append(str(val) if pd.notnull(val) else "")

        # 2. Batch Translate
        translated_list = translator.translate_batch(to_translate)

        # 3. Map back and Rebuild Rows
        cursor = 0
        data['name'] = translated_list[cursor]
        cursor += 1

        for s in sections:
            old_cols = data[s]['columns']
            # Rebuild Headers
            new_cols = []
            for _ in old_cols:
                new_cols.append(translated_list[cursor])
                cursor += 1
            
            # Rebuild Rows with new translated keys
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
    except: crops = []
    return render_template('index.html', crops=crops)

@app.route('/get_crop', methods=['POST'])
def get_crop():
    user_search = request.form.get('search_box')
    target_lang = request.form.get('language', 'en')
    result = get_translated_crop_data(user_search, target_lang)
    if result: return render_template('results.html', data=result)
    return "Crop not found!"

if __name__ == '__main__':
    if not os.path.exists('flask_cache'): os.makedirs('flask_cache')
    app.run(debug=True)
