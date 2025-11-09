# app.py の全体コード
from flask import Flask, render_template, request
from datetime import datetime, timedelta, date
import jpholiday
import os 
import math 

# --- Flask アプリケーションの初期化 ---
app = Flask(__name__) 

# --- 営業日・休日判定ロジック ---
def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if jpholiday.is_holiday(d):
        return False
    return True

def calculate_business_days_ago(end_date: date, days_needed: int) -> date:
    if days_needed <= 0:
        return end_date
    current_date = end_date
    days_to_count = days_needed
    while not is_business_day(current_date):
        current_date -= timedelta(days=1)
    days_to_count -= 1 
    while days_to_count > 0:
        current_date -= timedelta(days=1) 
        if is_business_day(current_date):
            days_to_count -= 1 
    return current_date

# --- Flask ルーティング ---
@app.route('/', methods=['GET', 'POST'])
def index():
    all_schedules = []
    global_start_date = None
    gantt_fixed_start_date = None
    
    DEFAULT_PROCESS_NAMES = [
        'ピッキング', 'ピッキング監査', '一包化', '一包化監査',
        'ホチキス・テープ止め', 'ホチキス・テープ止め監査', 
        'カレンダーセット', 'カレンダー監査'
    ]
    
    process_names = request.form.getlist('process_name[]') or DEFAULT_PROCESS_NAMES
    delivery_names_form = request.form.getlist('delivery_name[]')
    
    if request.method == 'POST':
        num_deliveries = len(delivery_names_form)
        earliest_start_date_obj = None
        
        for d_index in range(num_deliveries):
            delivery_date_str = request.form.get(f'delivery_date_{d_index}')
            delivery_name = delivery_names_form[d_index]
            
            if not delivery_date_str:
                continue
                
            schedule = []
            
            try:
                delivery_date_obj = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
            except ValueError:
                continue
                
            current_end_date_obj = delivery_date_obj
            while not is_business_day(current_end_date_obj):
                current_end_date_obj -= timedelta(days=1)

            first_process_start_date = None 

            for p_index, p_name in reversed(list(enumerate(process_names))):
                days_key = f'process_{p_index}_days_{d_index}'
                days_str = request.form.get(days_key, '0')
                
                try:
                    days_needed = math.ceil(float(days_str)) 
                except ValueError:
                    days_needed = 0

                end_date_obj = current_end_date_obj
                
                if days_needed > 0:
                    
                    start_date_obj = calculate_business_days_ago(end_date_obj, days_needed)
                    
                    schedule.append({
                        'name': p_name,
                        'start': start_date_obj.strftime('%Y-%m-%d'),
                        'end': end_date_obj.strftime('%Y-%m-%d'), 
                    })

                    if first_process_start_date is None or p_index == 0:
                         first_process_start_date = start_date_obj
                    
                    current_end_date_obj = start_date_obj - timedelta(days=1)
                    while not is_business_day(current_end_date_obj):
                        current_end_date_obj -= timedelta(days=1)
                        
                elif days_needed == 0:
                    current_end_date_obj -= timedelta(days=1)
                    while not is_business_day(current_end_date_obj):
                        current_end_date_obj -= timedelta(days=1)
            
            schedule.reverse()

            delivery_start_date_obj = first_process_start_date if first_process_start_date else delivery_date_obj

            if earliest_start_date_obj is None or delivery_start_date_obj < earliest_start_date_obj:
                earliest_start_date_obj = delivery_start_date_obj
                
            all_schedules.append({
                'delivery_name': delivery_name,
                'delivery_date': delivery_date_str,
                'schedule': schedule,
                'start_date': delivery_start_date_obj.strftime('%Y-%m-%d')
            })

        global_start_date = earliest_start_date_obj.strftime('%Y-%m-%d') if earliest_start_date_obj else None
        
        if global_start_date and earliest_start_date_obj:
            gantt_fixed_start_date = calculate_business_days_ago(
                earliest_start_date_obj, 2
            ).strftime('%Y-%m-%d')
        else:
             gantt_fixed_start_date = datetime.now().strftime('%Y-%m-%d')

    else:
        today = date.today()
        gantt_fixed_start_date = calculate_business_days_ago(
            today + timedelta(days=1), 2
        ).strftime('%Y-%m-%d')

    # ★ 修正済み: k: v を k, v に変更 (SyntaxError解消)
    form_data = {k: v for k, v in request.form.items()}
    
    return render_template(
        'index.html',
        all_schedules=all_schedules,
        global_start_date=global_start_date,
        gantt_fixed_start_date=gantt_fixed_start_date,
        delivery_names_form=delivery_names_form,
        process_names_form=process_names,
        request=request, 
        process_days_form=form_data
    )

if __name__ == '__main__':
    app.run(debug=True)