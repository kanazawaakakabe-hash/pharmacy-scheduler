from flask import Flask, render_template, request
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# 工程名のデフォルト設定
DEFAULT_PROCESS_NAMES = ['ピッキング', 'ピッキング監査', '一包化', '一包化監査', 'ホチキス・テープ止め', 'ホチキス・テープ止め監査', 'カレンダーセット', 'カレンダー監査']
DEFAULT_DELIVERY_NAMES = ["納品先1"]

def is_holiday(date):
    """土日を休日として判定"""
    return date.weekday() >= 5 

def calculate_previous_business_day(start_date, business_days):
    """営業日を指定日数分、過去に遡る"""
    current_date = start_date
    days_to_subtract = int(business_days)
    while days_to_subtract > 0:
        current_date -= timedelta(days=1)
        if not is_holiday(current_date):
            days_to_subtract -= 1
    while is_holiday(current_date):
        current_date -= timedelta(days=1)
    return current_date

@app.route('/', methods=['GET', 'POST'])
def index():
    global_start_date = None
    all_schedules = []
    delivery_names_form = DEFAULT_DELIVERY_NAMES
    process_days_form = {}
    process_names_form = DEFAULT_PROCESS_NAMES
    
    if request.method == 'POST':
        try:
            delivery_names_form = request.form.getlist('delivery_name[]')
            process_names_form = request.form.getlist('process_name[]')
            if not process_names_form or process_names_form == ['']:
                process_names_form = DEFAULT_PROCESS_NAMES
            
            earliest_start_date = datetime(2100, 1, 1).date() 

            for d_index, delivery_name in enumerate(delivery_names_form):
                delivery_date_str = request.form.get(f'delivery_date_{d_index}')
                if not delivery_date_str: continue 

                delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                current_end_date = delivery_date
                delivery_schedule = []
                
                # 納品日が休日なら直前の営業日に
                while is_holiday(current_end_date):
                    current_end_date -= timedelta(days=1)
                
                # 各工程を逆算
                for p_index, process_name in reversed(list(enumerate(process_names_form))):
                    days_key = f'process_{p_index}_days_{d_index}'
                    days_str = request.form.get(days_key)
                    process_days_form[days_key] = days_str or '1'
                    
                    if not days_str or not days_str.isdigit(): continue
                    process_days = int(days_str)
                    if process_days == 0: continue
                          
                    process_start_date = calculate_previous_business_day(current_end_date, process_days)
                    delivery_schedule.append({
                        'name': process_name,
                        'start': process_start_date.strftime('%Y-%m-%d'),
                        'end': current_end_date.strftime('%Y-%m-%d')
                    })
                    current_end_date = process_start_date

                delivery_schedule.reverse()
                if current_end_date < earliest_start_date:
                    earliest_start_date = current_end_date
                
                all_schedules.append({
                    'delivery_name': delivery_name,
                    'delivery_date': delivery_date_str,
                    'start_date': current_end_date.strftime('%Y-%m-%d'),
                    'schedule': delivery_schedule
                })
            if earliest_start_date.year != 2100:
                global_start_date = earliest_start_date.strftime('%Y-%m-%d')
        except Exception as e:
            print(f"計算エラー: {e}")
            global_start_date = "エラーが発生しました"
            
    else:
        # 初回ロード時（GET）
        for p_index, _ in enumerate(DEFAULT_PROCESS_NAMES):
            process_days_form[f'process_{p_index}_days_0'] = '1'

    return render_template(
        'index.html',
        global_start_date=global_start_date,
        all_schedules=all_schedules,
        delivery_names_form=delivery_names_form,
        process_days_form=process_days_form,
        process_names_form=process_names_form, 
        delivery_dates_form={}, # クラッシュ防止用
        request=request 
    )

if __name__ == '__main__':
    # Render環境用ポート設定
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)