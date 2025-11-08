from flask import Flask, render_template, request
from datetime import datetime, timedelta, date
import jpholiday
import os 
import math 

# --- Flask アプリケーションの初期化 ---
app = Flask(__name__) 


# --- 営業日・休日判定ロジック ---

def is_business_day(d: date) -> bool:
    """指定された日が営業日（平日かつ祝日ではない）であるかを判定する。"""
    # 土曜日(5) または 日曜日(6)
    if d.weekday() >= 5:
        return False
    # 日本の祝日
    if jpholiday.is_holiday(d):
        return False
    return True

def calculate_business_days_ago(end_date: date, days_needed: int) -> date:
    """指定された日数（営業日、1日単位）だけ過去に遡った日付を計算する関数。
    end_date は '作業最終日'（この工程の終了日）を指します。
    戻り値は '作業開始日' です。
    """
    if days_needed <= 0:
        return end_date
    
    current_date = end_date
    days_to_count = days_needed
    
    # 1. 終了日が非営業日の場合、最も近い過去の営業日を終了日とする
    while not is_business_day(current_date):
        current_date -= timedelta(days=1)
        
    # 2. 終了日自体を1日目の作業日としてカウント
    days_to_count -= 1 

    # 3. 残りの日数を遡ってカウント
    while days_to_count > 0:
        current_date -= timedelta(days=1) # 過去へ1日進む
        
        if is_business_day(current_date):
            days_to_count -= 1 # 営業日なら1日分カウントダウン
            
    # ループを抜けたcurrent_dateは作業開始日となる
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

            # 最初の工程の開始日を追跡するための変数
            first_process_start_date = None 

            # 工程を逆順で処理
            for p_index, p_name in reversed(list(enumerate(process_names))):
                days_key = f'process_{p_index}_days_{d_index}'
                days_str = request.form.get(days_key, '0')
                
                try:
                    # 小数点以下を切り上げて整数化
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

                    # 最も最初の工程の開始日を記録
                    if first_process_start_date is None or p_index == 0:
                         first_process_start_date = start_date_obj
                    
                    # 次の工程の完了日を更新
                    current_end_date_obj = start_date_obj - timedelta(days=1)
                    while not is_business_day(current_end_date_obj):
                        current_end_date_obj -= timedelta(days=1)
                        
                elif days_needed == 0:
                    # 所要日数が0の場合、次の工程の完了日を、現在の工程の完了日の前営業日として設定する
                    current_end_date_obj -= timedelta(days=1)
                    while not is_business_day(current_end_date_obj):
                        current_end_date_obj -= timedelta(days=1)
            
            schedule.reverse()

            # delivery_start_date_obj は最初の工程の開始日
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

    # ★ 修正済み: k: v を k, v に変更
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