import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for
from collections import defaultdict
import locale
from typing import List

# Flaskアプリケーションの初期化
app = Flask(__name__)

# ロケールの設定（日本の曜日表示などに影響）
try:
    locale.setlocale(locale.LC_TIME, 'ja_JP.UTF-8')
except locale.Error:
    try:
        # 環境によっては 'ja_JP' のみが必要な場合がある
        locale.setlocale(locale.LC_TIME, 'ja_JP')
    except locale.Error:
        print("警告: 日本語ロケールの設定に失敗しました。日付表示が英語になる可能性があります。")


# ----------------------------------------------------
# 1. マスターデータ（工程名、納品先名）
# ----------------------------------------------------

DEFAULT_PROCESS_NAMES = [
    'ピッキング',
    'ピッキング監査',
    '一包化',
    '一包化監査',
    'ホチキス・テープ止め',
    'ホチキス・テープ止め監査',
    'カレンダーセット',
    'カレンダー監査',
    '納品準備'
]

DEFAULT_DELIVERY_NAMES = ['納品先A', '納品先B']


# ----------------------------------------------------
# 2. 祝日対応ロジック（JSONファイルからの読み込み）
# ----------------------------------------------------

HOLIDAY_FILENAMES = [
    'holidays_2025.json',
    'holidays_2026.json',
    'holidays_2027.json'
]

def initialize_holiday_dates() -> set:
    """JSONファイル群から祝日を読み込み、datetime.dateオブジェクトのセットとして統合する"""
    all_holiday_dates = set()
    
    for filename in HOLIDAY_FILENAMES:
        # ファイルが存在しない場合は読み飛ばす
        if not os.path.exists(filename):
            print(f"🚨 警告: 祝日ファイル {filename} が見つかりません。")
            continue
            
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                for entry in data:
                    date_str = entry.get("date")
                    if date_str:
                        # YYYY-MM-DD 形式から datetime.date オブジェクトに変換
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                        all_holiday_dates.add(date_obj)
                        
            print(f"✅ 祝日データ: {filename} を正常に読み込みました。")
            
        except json.JSONDecodeError:
            print(f"🚨 警告: 祝日ファイル {filename} の形式が不正です。")
            
    return all_holiday_dates

# アプリケーション起動時に祝日データを初期化
HOLIDAY_DATES = initialize_holiday_dates()


def is_holiday(date: datetime.date) -> bool:
    """指定された日付が、土日または祝日リストに含まれているかを判定する"""
    # 1. 土日チェック (月曜日=0, 日曜日=6)
    if date.weekday() >= 5: 
        return True
    
    # 2. 祝日リストチェック
    if date in HOLIDAY_DATES:
        return True

    return False


# ----------------------------------------------------
# 3. コア計算ロジック
# ----------------------------------------------------

def calculate_previous_business_day(start_date: datetime.date, business_days: str) -> datetime.date:
    """
    指定された営業日数から日付を逆算する（土日・祝日を除外）
    """
    try:
        days_to_subtract = int(business_days)
    except ValueError:
        # 入力が不正な場合は0日として処理
        days_to_subtract = 0

    current_date = start_date
    
    # 逆算開始日が休日であった場合、直前の営業日にずらす
    while is_holiday(current_date):
        current_date -= timedelta(days=1)
    
    # 必要な営業日数分、日付を遡る
    while days_to_subtract > 0:
        current_date -= timedelta(days=1)
        # 休日（土日または祝日）でなければカウントを減らす
        if not is_holiday(current_date): 
            days_to_subtract -= 1
            
    # 計算された開始日が休日だった場合、直前の営業日に戻す
    while is_holiday(current_date):
        current_date -= timedelta(days=1)
        
    return current_date


# ----------------------------------------------------
# 4. Flask ルーティング
# ----------------------------------------------------

@app.route('/', methods=['GET', 'POST'])
def index():
    # フォームデータのデフォルト値と結果の初期化
    delivery_names_form = DEFAULT_DELIVERY_NAMES
    process_names_form = DEFAULT_PROCESS_NAMES
    process_days_form = defaultdict(str)
    
    # スケジュール結果の初期化
    global_start_date = None
    all_schedules = defaultdict(list)
    gantt_fixed_start_date = None
    
    # POSTリクエストの場合（フォーム送信時）
    if request.method == 'POST':
        # 納品希望日の取得
        delivery_date_str = request.form.get('delivery_date')
        if not delivery_date_str:
            return redirect(url_for('index')) # 日付がない場合はリダイレクト

        delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()

        # フォームから納品先名と工程名、日数を取得
        delivery_names_form = request.form.getlist('delivery_name[]')
        
        # フォームから送られた工程名（JSで編集された最新のリスト）を取得
        posted_process_names = request.form.getlist('process_name[]')
        if posted_process_names:
            process_names_form = [name for name in posted_process_names if name] # 空の要素を除外

        # 最小の開始日（全体のプロジェクト開始日）を格納するリスト
        all_start_dates = []

        # 納品先ごとにスケジュールを計算
        for d_index, delivery_name in enumerate(delivery_names_form):
            current_date = delivery_date # 納品先ごとの処理開始は納品希望日から

            # 工程ごとに逆算処理
            schedule = []
            
            # 工程を逆順に処理（納品準備から逆算）
            for p_index, process_name in reversed(list(enumerate(process_names_form))):
                key = f'process_{p_index}_days_{d_index}'
                days_str = request.form.get(key) or '0'
                process_days_form[key] = days_str # フォームに再表示するために保存
                
                days = int(days_str)
                
                if days > 0:
                    # 開始日を計算
                    start_date = calculate_previous_business_day(current_date, days_str)
                    
                    # 終了日（計算された次の工程の開始日）は current_date の前日
                    end_date = current_date - timedelta(days=1)
                    
                    # 逆算ロジックにより、計算された開始日が休日だった場合、さらに遡る処理を含めているため、
                    # ここではシンプルに結果を格納
                    schedule.insert(0, {
                        'name': process_name,
                        'start': start_date,
                        'end': end_date,
                        'days': days
                    })
                    
                    # 次の工程の終了日は、今回の工程の開始日
                    current_date = start_date
                
                elif days == 0:
                    # 0日の工程の場合、日付は変わらないがスケジュールに追加
                    schedule.insert(0, {
                        'name': process_name,
                        'start': current_date, # 開始日と終了日が同じ
                        'end': current_date,
                        'days': 0
                    })

            # 納品先ごとのスケジュールと全体開始日を記録
            all_schedules[delivery_name] = schedule
            if schedule:
                # 最後の工程の開始日が、その納品先グループの全体の開始日となる
                group_start_date = schedule[0]['start']
                all_start_dates.append(group_start_date)

        # 全体の発注開始日（最も早い開始日）を決定
        if all_start_dates:
            global_start_date = min(all_start_dates)
        
        # ガントチャートの表示基準日（最も早い開始日、または納品希望日のいずれか早い方から固定日数を逆算）
        # 現在は納品希望日から固定日数を逆算するロジックを維持
        fixed_offset_days = 60 # ガントチャートに表示する期間のオフセット
        # 逆算処理は不要。シンプルに、納品希望日以前の固定日数を取得
        gantt_start_day = delivery_date - timedelta(days=fixed_offset_days)
        gantt_fixed_start_date = gantt_start_day.strftime('%Y-%m-%d')
        
    # GETリクエストの場合 (初回ロード)
    else:
        # デフォルトの納品先1に対して、デフォルトの日数をセット
        for p_index, _ in enumerate(DEFAULT_PROCESS_NAMES):
            # デフォルトで「1日」をセット
            process_days_form[f'process_{p_index}_days_0'] = '1'

    # Jinjaへのデータ引き渡し
    
    # HOLIDAY_DATES (datetime.dateオブジェクトのセット) を文字列リストに変換してJSに渡す
    holiday_dates_str = [date.strftime('%Y-%m-%d') for date in HOLIDAY_DATES]
    
    return render_template(
        'index.html',
        global_start_date=global_start_date,
        all_schedules=all_schedules,
        delivery_names_form=delivery_names_form,
        process_days_form=process_days_form,
        # マスターデータとして、現在の工程名リストをJSに渡す
        process_names_form=process_names_form, 
        gantt_fixed_start_date=gantt_fixed_start_date,
        HOLIDAYS_LIST=holiday_dates_str, # ★祝日リストを追加
        request=request
    )


if __name__ == '__main__':
    # 開発環境での実行
    app.run(debug=True, port=5001)