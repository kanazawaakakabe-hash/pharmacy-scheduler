from flask import Flask, render_template, request
from datetime import datetime, timedelta, date
import jpholiday
import os # ★ テンプレートパス指定のためにOSモジュールを追加

# --- Flask アプリケーションの初期化 ---
# template_folderにアプリケーションのルートディレクトリ（app.pyがある場所）を明示的に指定
# これにより、Render環境下でFlaskがindex.htmlを確実に見つけられるようになります。
app = Flask(__name__, template_folder=os.path.dirname(os.path.abspath(__file__))) 

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
    """指定された日数（営業日、1日単位）だけ過去に遡った日付を計算する関数。"""
    current_date = start_date
    # 所要営業日数が0の場合は、次の工程の開始日（start_date）がそのまま開始日
    if days_needed == 0:
        return start_date

    days_to_count = days_needed 

    # 最初の処理は、次の工程の開始日(start_date)の「前日」から開始
    current_date -= timedelta(days=1)
    
    while days_to_count > 0:
        if is_business_day(current_date):
            days_to_count -= 1 # 営業日なら1日分カウントダウン

        # カウントが残っている場合、さらに過去へ進む
        if days_to_count > 0:
             current_date -= timedelta(days=1)
        # days_to_count == 0 の場合、ループを抜けたcurrent_dateは作業開始日の前日になっている
    
    # 最終的な開始日を返す（ループを抜けたcurrent_dateの翌日が開始日）
    return current_date + timedelta(days=1)


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
    
    # フォームデータから工程名、納品先名を取得
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
                
            # 納品日（最終工程の終了日）が営業日になるまで逆算
            current_end_date_obj = delivery_date_obj
            while not is_business_day(current_end_date_obj):
                current_end_date_obj -= timedelta(days=1)

            # 工程を逆順で処理
            for p_index, p_name in reversed(list(enumerate(process_names))):
                days_key = f'process_{p_index}_days_{d_index}'
                days_str = request.form.get(days_key, '0')
                try:
                    # 1日単位のためintに変換
                    # HTML側でstep="0.5"が許容されても、Python側は営業日単位で処理
                    days_needed = int(float(days_str)) 
                except ValueError:
                    days_needed = 0

                if days_needed > 0:
                    
                    # 1. 開始日を逆算
                    start_date_obj = calculate_business_days_ago(current_end_date_obj, days_needed)
                    
                    # 2. この工程の終了日 (作業が完了した日) を計算
                    # 作業が完了するのは、次の工程が始まる日の前日（営業日）。
                    end_date_obj = current_end_date_obj - timedelta(days=1) 
                    
                    # 終了日が営業日ではない場合はさらに過去に遡る（作業は営業日に完了するため）
                    while not is_business_day(end_date_obj):
                         end_date_obj -= timedelta(days=1)
                    
                    schedule.append({
                        'name': p_name,
                        'start': start_date_obj.strftime('%Y-%m-%d'),
                        'end': end_date_obj.strftime('%Y-%m-%d'), # 完了した日を記録
                    })
                    
                    # 次の工程の開始日を更新
                    current_end_date_obj = start_date_obj 
                
                elif days_needed == 0:
                    # 所要日数が0の場合、次の工程（逆算のため一つ前の工程）の開始日はそのまま
                    # current_end_date_objを維持
                    pass
            
            schedule.reverse()

            delivery_start_date_obj = current_end_date_obj

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
        if global_start_date:
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