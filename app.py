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
    
    # Renderでデプロイする場合、ファイルパスはルートディレクトリを基準とする
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    for filename in HOLIDAY_FILENAMES:
        file_path = os.path.join(base_dir, filename)
        
        if not os.path.exists(file_path):
            print(f"🚨 警告: 祝日ファイル {filename} が見つかりません。")
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
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
        days_to_subtract = 0

    current_date = start_date
    
    # 逆算開始日が休日であった場合、直前の営業日にずらす
    while is_holiday(current_date):
        current_date -= timedelta(days=1)
    
    # 必要な営業日数分、日付を遡る
    while days_to_subtract > 0:
        current_date -= timedelta(days=1)
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
    
    global_start_date = None
    all_schedules = defaultdict(list)
    gantt_fixed_start_date = None
    
    if request.method == 'POST':
        # 納品希望日の取得
        delivery_date_str = request.form.get('delivery_date')
        if not delivery_date_str:
            # 納品希望日が空の場合は、計算結果をクリアして初期状態に戻す
            return render_template(
                'index.html',
                global_start_date=None,
                all_schedules={},
                delivery_names_form=DEFAULT_DELIVERY_NAMES,
                process_days_form={},
                process_names_form=DEFAULT_PROCESS_NAMES, 
                gantt_fixed_start_date=None,
                HOLIDAYS_LIST=[],
                request=request
            )

        delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()

        # フォームから納品先名と工程名、日数を取得
        delivery_names_form = request.form.getlist('delivery_name[]')
        
        posted_process_names = request.form.getlist('process_name[]')
        if posted_process_names:
            process_names_form = [name for name in posted_process_names if name]

        all_start_dates = []

        for d_index, delivery_name in enumerate(delivery_names_form):
            current_date = delivery_date 

            schedule = []
            
            for p_index, process_name in reversed(list(enumerate(process_names_form))):
                key = f'process_{p_index}_days_{d_index}'
                days_str = request.form.get(key) or '0'
                process_days_form[key] = days_str
                
                days = int(days_str)
                
                if days > 0:
                    start_date = calculate_previous_business_day(current_date, days_str)
                    end_date = current_date - timedelta(days=1)
                    
                    schedule.insert(0, {
                        'name': process_name,
                        'start': start_date,
                        'end': end_date,
                        'days': days
                    })
                    
                    current_date = start_date
                
                elif days == 0:
                    schedule.insert(0, {
                        'name': process_name,
                        'start': current_date,
                        'end': current_date,
                        'days': 0
                    })

            all_schedules[delivery_name] = schedule
            if schedule:
                group_start_date = schedule[0]['start']
                all_start_dates.append(group_start_date)

        if all_start_dates:
            global_start_date = min(all_start_dates)
        
        fixed_offset_days = 60
        gantt_start_day = delivery_date - timedelta(days=fixed_offset_days)
        gantt_fixed_start_date = gantt_start_day.strftime('%Y-%m-%d')
        
    else:
        # GETリクエスト（初回ロード）
        for p_index, _ in enumerate(DEFAULT_PROCESS_NAMES):
            process_days_form[f'process_{p_index}_days_0'] = '1'

    # Jinjaへのデータ引き渡し
    holiday_dates_str = [date.strftime('%Y-%m-%d') for date in HOLIDAY_DATES]
    
    return render_template(
        'index.html',
        global_start_date=global_start_date,
        all_schedules=all_schedules,
        delivery_names_form=delivery_names_form,
        process_days_form=process_days_form,
        process_names_form=process_names_form, 
        gantt_fixed_start_date=gantt_fixed_start_date,
        HOLIDAYS_LIST=holiday_dates_str,
        request=request
    )


if __name__ == '__main__':
    # 開発環境での実行
    app.run(debug=True, port=5001)