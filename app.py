from flask import Flask, render_template, request
from datetime import datetime, timedelta

app = Flask(__name__)

# ★★★ デフォルト工程名の定義 ★★★
DEFAULT_PROCESS_NAMES = [
    'ピッキング',
    'ピッキング監査',
    '一包化',
    '一包化監査',
    'ホチキス・テープ止め',
    'ホチキス・テープ止め監査',
    'カレンダーセット',
    'カレンダー監査'
]

# デフォルトで表示する納品先グループの初期値
DEFAULT_DELIVERY_NAMES = ["納品先1"]

# 休日をチェックするシンプルな関数 (土日のみ)
def is_holiday(date):
    # 月曜日=0, 日曜日=6
    return date.weekday() >= 5 

# 営業日数から日付を逆算する関数
def calculate_previous_business_day(start_date, business_days):
    current_date = start_date
    days_to_subtract = int(business_days)
    
    while days_to_subtract > 0:
        current_date -= timedelta(days=1)
        # 営業日であればカウントを減らす
        if not is_holiday(current_date):
            days_to_subtract -= 1
            
    # 計算された開始日が休日だった場合、直前の営業日に戻す（このロジックでは起きにくいが念のため）
    while is_holiday(current_date):
        current_date -= timedelta(days=1)
        
    return current_date

# ★★★ ガントチャート開始日を「入力日の翌週月曜日」に固定する関数 ★★★
def calculate_gantt_start_date(today_date):
    # Pythonの weekday() は月曜日=0, 日曜日=6です。
    days_to_add = (7 - today_date.weekday())
    
    return today_date + timedelta(days=days_to_add)


@app.route('/', methods=['GET', 'POST'])
def index():
    global_start_date = None
    all_schedules = []
    
    # フォームデータを保持するためのディクショナリ
    delivery_names_form = DEFAULT_DELIVERY_NAMES
    process_days_form = {} # { 'process_0_days_0': '1', ... }
    process_names_form = DEFAULT_PROCESS_NAMES
    
    # 3. ガントチャート固定開始日を計算
    # サーバーの現在時刻を基準に入力日（当日）とする
    today = datetime.now().date()
    gantt_fixed_start_date = calculate_gantt_start_date(today).strftime('%Y-%m-%d')


    if request.method == 'POST':
        try:
            # フォームデータの取得
            delivery_names_form = request.form.getlist('delivery_name[]')
            process_names_form = request.form.getlist('process_name[]')
            
            # 工程名が空の場合はデフォルトを使用 (安全策)
            if not process_names_form or process_names_form == ['']:
                 process_names_form = DEFAULT_PROCESS_NAMES
            
            # 全納品先で最も早い発注開始日を追跡
            earliest_start_date = datetime(2100, 1, 1).date() 

            for d_index, delivery_name in enumerate(delivery_names_form):
                delivery_date_str = request.form.get(f'delivery_date_{d_index}')
                
                if not delivery_date_str:
                    continue 

                delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
                
                current_end_date = delivery_date
                delivery_schedule = []
                
                # 納品希望日が休日であれば、直前の営業日に修正
                while is_holiday(current_end_date):
                    current_end_date -= timedelta(days=1)
                
                # スケジュールの逆算
                for p_index, process_name in reversed(list(enumerate(process_names_form))):
                    days_key = f'process_{p_index}_days_{d_index}'
                    days_str = request.form.get(days_key)
                    
                    # フォームデータ保持用のディクショナリに保存
                    process_days_form[days_key] = days_str or '1' # 空の場合は'1'をセット
                    
                    if not days_str or not days_str.isdigit():
                        continue
                    
                    process_days = int(days_str)
                    
                    if process_days == 0:
                         continue
                          
                    # 工程の開始日を逆算
                    process_start_date = calculate_previous_business_day(current_end_date, process_days)

                    # スケジュールに追加 (YYYY-MM-DD 形式の文字列のみ)
                    delivery_schedule.append({
                        'name': process_name,
                        'start': process_start_date.strftime('%Y-%m-%d'),
                        # 工程の終了日（次の工程の開始日、または納品日）
                        'end': current_end_date.strftime('%Y-%m-%d'), 
                        'days': process_days
                    })
                    
                    # 次の工程の終了日を更新
                    current_end_date = process_start_date

                # スケジュールを逆順に並べ替え（ピッキング -> 納品）
                delivery_schedule.reverse()
                
                # 全体発注開始日の更新
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
            # エラー処理
            print(f"計算エラー: {e}")
            global_start_date = "計算エラーが発生しました。"
            
    # GETリクエストの場合 (初回ロード)
    else:
        # フォームのデフォルト値をセット
        process_names_form = DEFAULT_PROCESS_NAMES
        delivery_names_form = DEFAULT_DELIVERY_NAMES
        
        # デフォルトの納品先1に対して、デフォルトの日数をセット
        for p_index, _ in enumerate(DEFAULT_PROCESS_NAMES):
            process_days_form[f'process_{p_index}_days_0'] = '1'

    return render_template(
        'index.html',
        global_start_date=global_start_date,
        all_schedules=all_schedules,
        delivery_names_form=delivery_names_form,
        process_days_form=process_days_form,
        process_names_form=process_names_form, 
        gantt_fixed_start_date=gantt_fixed_start_date, 
        # ★★★ 修正箇所：未定義エラーを回避するため空の辞書を渡す ★★★
        delivery_dates_form={},
        request=request 
    )

if __name__ == '__main__':
    app.run(debug=True, port=5001)