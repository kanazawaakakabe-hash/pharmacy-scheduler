from flask import Flask, render_template, request
from datetime import datetime, timedelta, date
import jpholiday
import os 

# --- Flask アプリケーションの初期化 ---
# index.html は 'templates/' フォルダにあるため、標準設定に戻します。
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

def calculate_business_days_ago(start_date: date, days_needed: int) -> date:
    """指定された日数（営業日、1日単位）だけ過去に遡った日付を計算する関数。
    
    start_date は '作業最終日'（この工程の終了日）を指します。
    戻り値は '作業開始日' です。
    """
    if days_needed == 0:
        # 所要日数が0の場合、開始日は終了日の翌日（次の工程の開始日）として扱うため、ここでは終了日をそのまま返す
        return start_date 

    current_date = start_date
    days_to_count = days_needed - 1 # 終了日自体を1日目としてカウント開始

    # 終了日が営業日ではない場合、最も近い過去の営業日に合わせる
    while not is_business_day(current_date):
        current_date -= timedelta(days=1)
        
    # 終了日自体を作業日としてカウントしているため、1日分は既に考慮済み
    
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
                
            # 納品日 (delivery_date_obj) を最終工程の「作業終了日」として設定
            current_end_date_obj = delivery_date_obj
            
            # 納品希望日が非営業日なら、最も近い過去の営業日を「最終作業完了日」とする
            while not is_business_day(current_end_date_obj):
                current_end_date_obj -= timedelta(days=1)

            # 工程を逆順で処理
            for p_index, p_name in reversed(list(enumerate(process_names))):
                days_key = f'process_{p_index}_days_{d_index}'
                days_str = request.form.get(days_key, '0')
                try:
                    days_needed = int(float(days_str)) 
                except ValueError:
                    days_needed = 0

                # この工程の終了日 (作業完了日) は current_end_date_obj
                end_date_obj = current_end_date_obj
                
                if days_needed > 0:
                    
                    # 1. 開始日を逆算 (end_date_obj は作業最終日)
                    start_date_obj = calculate_business_days_ago(end_date_obj, days_needed)
                    
                    schedule.append({
                        'name': p_name,
                        'start': start_date_obj.strftime('%Y-%m-%d'),
                        'end': end_date_obj.strftime('%Y-%m-%d'), 
                    })
                    
                    # 2. 次の工程の完了日を更新
                    # 次の工程の完了日は、現在の工程の開始日（start_date_obj）の「前営業日」
                    
                    current_end_date_obj = start_date_obj - timedelta(days=1)
                    # 営業日になるまでさらに過去に遡る
                    while not is_business_day(current_end_date_obj):
                        current_end_date_obj -= timedelta(days=1)
                        
                elif days_needed == 0:
                    # 所要日数が0の場合、次の工程（逆算のため一つ前の工程）の完了日を、現在の工程の完了日の前営業日として設定する
                    current_end_date_obj -= timedelta(days=1)
                    while not is_business_day(current_end_date_obj):
                        current_end_date_obj -= timedelta(days=1)
            
            schedule.reverse()

            # delivery_start_date_obj は最初の工程の開始日。この開始日を特定する。
            if schedule:
                # 最初の工程の開始日を全体の開始日とする
                delivery_start_date_obj = datetime.strptime(schedule[0]['start'], '%Y-%m-%d').date()
            else:
                # 所要日数が全て0の場合、納品日の前営業日を全体の開始日とする（暫定）
                delivery_start_date_obj = delivery_date_obj - timedelta(days=1)
                while not is_business_day(delivery_start_date_obj):
                    delivery_start_date_obj -= timedelta(days=1)


            if earliest_start_date_obj is None or delivery_start_date_obj < earliest_start_date_obj:
                earliest_start_date_obj = delivery_start_date_obj
                
            all_schedules.append({
                'delivery_name': delivery_name,
                'delivery_date': delivery_date_str,
                'schedule': schedule,
                'start_date': delivery_start_date_obj.strftime('%Y-%m-%d')
            })

        global_start_date = earliest_start_date_obj.strftime('%Y-%m-%d') if earliest_start_date_obj else None
        
        # ガントチャートの表示開始日を、全体開始日の2営業日前に設定
        if global_start_date and earliest_start_date_obj:
            gantt_fixed_start_date = calculate_business_days_ago(
                earliest_start_date_obj, 2
            ).strftime('%Y-%m-%d')
        else:
             # スケジュール計算が行われなかった場合は今日の日付をセット
             gantt_fixed_start_date = datetime.now().strftime('%Y-%m-%d')

    else:
        # GETリクエストの場合、今日の2営業日前の日付を初期値としてセット
        today = date.today()
        gantt_fixed_start_date = calculate_business_days_ago(
            today + timedelta(days=1), 2
        ).strftime('%Y-%m-%d')

    # フォームの値を維持するためにJinjaに渡す
    form_data = {k: v for k, v in request.form.items()}
    
    return render_template(
        'index.html', # テンプレートファイル名
        all_schedules=all_schedules,
        global_start_date=global_start_date,
        gantt_fixed_start_date=gantt_fixed_start_date,
        delivery_names_form=delivery_names_form,
        process_names_form=process_names,
        request=request, 
        process_days_form=form_data
    )

if __name__ == '__main__':
    # ローカル実行用の設定
    app.run(debug=True)