import os
import pandas as pd
from flask import Flask, render_template, request, url_for
from deep_translator import GoogleTranslator
from flask_caching import Cache
from thefuzz import process 

app = Flask(__name__)

# Cache setup
cache = Cache(app, config={
    'CACHE_TYPE': 'FileSystemCache',
    'CACHE_DIR': 'flask_cache',
    'CACHE_DEFAULT_TIMEOUT': 604800
})

def translate_to_english(text, source_lang):
    if source_lang == 'en': return text
    try:
        return GoogleTranslator(source='auto', target='en').translate(text)
    except: return text

def parse_range(range_str, user_val):
    """Fixed: Converts user_val to float to avoid comparison errors"""
    try:
        if '-' in str(range_str):
            low, high = map(float, str(range_str).split('-'))
            return low <= float(user_val) <= high
        return False
    except: return False

def search_excel(english_input):
    try:
        # Added engine='openpyxl' for better compatibility on Render
        excel_data = pd.read_excel('database.xlsx', sheet_name=None, engine='openpyxl')
        clean_data = {str(k).strip().lower(): v for k, v in excel_data.items()}
        for s in clean_data:
            clean_data[s].columns = clean_data[s].columns.astype(str).str.strip().str.lower()

        df_names = clean_data.get('crop_name')
        crops_in_db = df_names['crop_name'].astype(str).tolist()
        
        best_match, score = process.extractOne(english_input, crops_in_db)
        if score < 60: return None

        match = df_names[df_names['crop_name'] == best_match].iloc[0]
        cid = match['crop_id']
        
        def get_info(key, crop_id):
            if key not in clean_data: return {"rows": [], "columns": []}
            df = clean_data[key]
            filtered = df[df['crop_id'] == crop_id].copy()
            cols = filtered.columns.tolist()[2:]
            return {"rows": filtered.to_dict('records'), "columns": cols}

        return {
            "name": str(match['crop_name']),
            "image": match.get('image_file', None), # Ensure this matches filename in static/
            "requirements": get_info('crop_requirement', cid),
            "steps": get_info('cultivation_step', cid),
            "risks": get_info('risk_associated', cid)
        }
    except Exception as e:
        print(f"DB Error: {e}")
        return None

@cache.memoize()
def get_translated_crop_data(user_input, target_lang):
    english_name = translate_to_english(user_input, target_lang)
    data = search_excel(english_name)
    if not data or target_lang == 'en': return data
    try:
        translator = GoogleTranslator(source='auto', target=target_lang)
        to_translate = [data['name']]
        sections = ['requirements', 'steps', 'risks']
        for s in sections:
            to_translate.extend([str(c) for c in data[s]['columns']])
            for row in data[s]['rows']:
                for col in data[s]['columns']:
                    val = row.get(col, "")
                    to_translate.append(str(val) if pd.notnull(val) else "")
        translated_list = translator.translate_batch(to_translate)
        cursor = 0
        data['name'] = translated_list[cursor]
        cursor += 1
        for s in sections:
            old_cols = data[s]['columns']
            new_cols = [translated_list[cursor + i] for i in range(len(old_cols))]
            cursor += len(old_cols)
            new_rows = []
            for _ in data[s]['rows']:
                new_row = {new_cols[i]: translated_list[cursor + i] for i in range(len(new_cols))}
                new_rows.append(new_row)
                cursor += len(new_cols)
            data[s]['columns'], data[s]['rows'] = new_cols, new_rows
        return data
    except: return data

@app.route('/')
def home():
    try:
        df = pd.read_excel('database.xlsx', sheet_name='crop_name', engine='openpyxl')
        crops = df.iloc[:, 1].dropna().unique().tolist()
    except: crops = []
    return render_template('index.html', crops=crops)

@app.route('/get_crop', methods=['POST'])
def get_crop():
    user_search = request.form.get('search_box')
    target_lang = request.form.get('language', 'en')
    result = get_translated_crop_data(user_search, target_lang)
    # Using 'result.html' as per your previous logs
    if result: return render_template('result.html', data=result)
    return f"Crop '{user_search}' not found!"

@app.route('/recommend', methods=['POST'])
def recommend():
    """Fixed: Added float conversion for user inputs"""
    try:
        n = request.form.get('n')
        p = request.form.get('p')
        k = request.form.get('k')
        
        df = pd.read_excel('database.xlsx', sheet_name='crop_name', engine='openpyxl')
        df.columns = df.columns.astype(str).str.strip().str.lower()
        
        recommended = [row['crop_name'] for _, row in df.iterrows() 
                       if parse_range(row.get('n_range'), n) and 
                          parse_range(row.get('p_range'), p) and 
                          parse_range(row.get('k_range'), k)]
        
        return render_template('index.html', crops=df.iloc[:,1].tolist(), rec_results=recommended)
    except Exception as e: 
        print(f"Recommend Error: {e}")
        return "Please enter numeric values for N, P, and K."

@app.route('/healthz')
def health_check():
    return "OK", 200

if __name__ == '__main__':
    if not os.path.exists('flask_cache'): os.makedirs('flask_cache')
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
