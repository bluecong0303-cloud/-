"""다원 딸기 농장 — 컴퓨터에 기록을 보관하는 Streamlit 앱.

사용: Python 3.11 이상에서 두 파일을 같은 폴더에 두고 아래 명령을 실행하세요.
  python -m pip install -r requirements.txt
  python -m streamlit run app.py

GitHub에는 app.py와 requirements.txt만 올리세요. 기존 BAZE 기록은 자동
이전하지 않아요. 이 앱에서 새로 입력한 기록은 실행한 컴퓨터의 사용자 폴더
아래 .dawon-farm/farm.sqlite3에 보관돼요. APP_DATA_DIR로 위치를 바꿀 수 있어요.
Streamlit Community Cloud의 임시 디스크는 영구 보관용이 아니에요.
이 버전은 개인 컴퓨터용이며 공개 로그인·결제·지도·AI 호출은 없어요.
상품 그림은 이모지이고, 판매량은 명확한 상품명과 kg/g만 분석해요.
메뉴를 이동해도 초안은 유지하지만 브라우저 새로고침 전에는 저장해 주세요.
"""

from __future__ import annotations

import calendar
import csv
import html
import io
import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import streamlit as st

MAX_GRAMS = 999_999_999
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))
);
CREATE TABLE IF NOT EXISTS stock (
 product_id TEXT PRIMARY KEY REFERENCES products(id),
 base_grams INTEGER CHECK(base_grams BETWEEN 0 AND 999999999),
 version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
 product_id TEXT NOT NULL REFERENCES products(id), day TEXT NOT NULL,
 body TEXT NOT NULL, version INTEGER NOT NULL,
 updated_at TEXT NOT NULL, PRIMARY KEY(product_id,day)
);
CREATE TABLE IF NOT EXISTS sales (
 source_product_id TEXT NOT NULL, day TEXT NOT NULL,
 product_id TEXT NOT NULL REFERENCES products(id),
 grams INTEGER NOT NULL CHECK(grams > 0),
 PRIMARY KEY(source_product_id,day,product_id),
 FOREIGN KEY(source_product_id,day) REFERENCES notes(product_id,day)
);
CREATE INDEX IF NOT EXISTS sales_product ON sales(product_id);
CREATE INDEX IF NOT EXISTS sales_day ON sales(day);
"""


class FarmError(ValueError):
    """수정 없이 사용자에게 보여 줄 수 있는 안내예요."""


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
    finally:
        db.close()


@contextmanager
def transaction(path: Path):
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def query(path: Path, sql: str, params=()) -> list[dict]:
    db = connect(path)
    try:
        return [dict(r) for r in db.execute(sql, params)]
    finally:
        db.close()


def kg(grams: int) -> str:
    return f'{Decimal(grams) / 1000:,.3f}'.rstrip('0').rstrip('.')


def parse_weight(text: str, unit: str = 'kg') -> int:
    if not re.fullmatch(r'\d+(?:\.\d+)?', text.strip()):
        raise FarmError('중량은 0 이상의 숫자로 적어 주세요.')
    try:
        value = Decimal(text) * (1000 if unit.lower() == 'kg' else 1)
    except InvalidOperation:
        raise FarmError('중량을 다시 확인해 주세요.') from None
    if value != value.to_integral_value() or value < 0 or value > MAX_GRAMS:
        raise FarmError('0~999,999.999kg, 1g 단위까지 입력할 수 있어요.')
    return int(value)


def parse_sales(body: str, products: list[dict], selected: str) -> dict[str, int]:
    text = body.strip()
    if not re.search(r'\d\s*(?:kg|g)\b', text, re.I):
        # A weight-like ambiguous sentence must not silently become a plain note.
        if re.search(r'\d\s*(?:킬로|키로|그램|킬로그램)|\d\s*(?:kg|g)', text, re.I):
            raise FarmError('판매량은 상품명과 kg 또는 g로 적어 주세요. 예: 딸기 2kg')
        return {}
    by_name = {p['name']: p['id'] for p in products}
    result: dict[str, int] = {}
    parts = re.split(r'[,，;\n+]+', text)
    for part in parts:
        if not part.strip():
            continue
        match = re.fullmatch(r'\s*(.*?)\s*(\d+(?:\.\d+)?)\s*(kg|g)\s*(?:판매)?\s*', part, re.I)
        if not match:
            raise FarmError('판매량을 명확히 적어 주세요. 예: 딸기 2kg, 상추 500g. 일반 메모와 판매 문장은 나누어 적어 주세요.')
        name, amount, unit = match.groups()
        pid = selected if not name.strip() else by_name.get(name.strip())
        if not pid:
            raise FarmError(f'“{name.strip()}” 상품을 찾지 못했어요. 등록된 이름을 그대로 적어 주세요.')
        grams = parse_weight(amount, unit)
        if grams <= 0:
            raise FarmError('판매량은 0보다 커야 해요. 취소하려면 메모의 판매량을 지워 주세요.')
        result[pid] = result.get(pid, 0) + grams
        if result[pid] > MAX_GRAMS:
            raise FarmError('판매량이 입력 가능한 범위를 넘었어요.')
    return result


def all_products(path: Path, archived=False) -> list[dict]:
    return query(path, 'SELECT * FROM products' + ('' if archived else ' WHERE archived=0') + ' ORDER BY rowid')


def stock_rows(path: Path) -> list[dict]:
    return query(path, '''SELECT p.*, s.base_grams, COALESCE(s.version,0) AS version,
        COALESCE((SELECT SUM(grams) FROM sales WHERE product_id=p.id),0) AS sold_grams
        FROM products p LEFT JOIN stock s ON s.product_id=p.id WHERE p.archived=0 ORDER BY p.rowid''')


def add_products(path: Path, raw: str) -> None:
    names = [n.strip() for n in raw.splitlines() if n.strip()]
    if not names or len(names) > 20:
        raise FarmError('상품 이름을 한 줄에 하나씩, 한 번에 1~20개 적어 주세요.')
    if any(len(n) > 40 or re.search(r'[,，;+\n]', n) for n in names):
        raise FarmError('상품명은 40자 이하로 적고 쉼표·더하기·세미콜론은 빼 주세요.')
    if len(set(names)) != len(names):
        raise FarmError('같은 이름이 중복됐어요.')
    with transaction(path) as db:
        for name in names:
            if db.execute('SELECT 1 FROM products WHERE name=?', (name,)).fetchone():
                raise FarmError(f'“{name}” 이름은 이미 사용 중이거나 보관돼 있어요.')
            pid = uuid.uuid4().hex
            db.execute('INSERT INTO products(id,name) VALUES (?,?)', (pid, name))
            db.execute('INSERT INTO stock(product_id) VALUES (?)', (pid,))


def save_stock(path: Path, changes: dict) -> None:
    parsed = {pid: (None if v['text'].strip() == '' else parse_weight(v['text'])) for pid, v in changes.items()}
    with transaction(path) as db:
        for pid, grams in parsed.items():
            row = db.execute('SELECT s.*,p.archived FROM stock s JOIN products p ON p.id=s.product_id WHERE product_id=?', (pid,)).fetchone()
            if not row or row['archived'] or row['version'] != changes[pid]['version']:
                raise FarmError('다른 창에서 재고가 변경됐어요. 초안을 복사한 뒤 기록을 새로 불러와 주세요.')
            sold = db.execute('SELECT COALESCE(SUM(grams),0) FROM sales WHERE product_id=?', (pid,)).fetchone()[0]
            if (grams is None and sold > 0) or (grams is not None and grams < sold):
                raise FarmError('준비한 재고가 이미 판매한 양보다 작아요. 재고는 바꾸지 않았어요.')
            db.execute('UPDATE stock SET base_grams=?,version=version+1 WHERE product_id=?', (grams, pid))


def save_note(path: Path, pid: str, day: str, body: str, expected: int) -> bool:
    if len(body) > 3000:
        raise FarmError('메모는 3,000자까지 적을 수 있어요.')
    try:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError
    except ValueError:
        raise FarmError('날짜를 확인해 주세요.') from None
    with transaction(path) as db:
        if not db.execute('SELECT 1 FROM products WHERE id=? AND archived=0', (pid,)).fetchone():
            raise FarmError('사용 중인 상품을 선택해 주세요.')
        old = db.execute('SELECT * FROM notes WHERE product_id=? AND day=?', (pid, day)).fetchone()
        version = old['version'] if old else 0
        if version != expected:
            raise FarmError('다른 창에서 메모가 바뀌었어요. 초안을 복사한 뒤 저장 기록을 다시 불러와 주세요.')
        if old and old['body'] == body:
            return False
        products = [dict(r) for r in db.execute('SELECT id,name FROM products WHERE archived=0')]
        new_sales = parse_sales(body, products, pid)
        previous = {r['product_id']: r['grams'] for r in db.execute('SELECT * FROM sales WHERE source_product_id=? AND day=?', (pid, day))}
        for product_id, grams in new_sales.items():
            row = db.execute('SELECT base_grams FROM stock WHERE product_id=?', (product_id,)).fetchone()
            name = next(p['name'] for p in products if p['id'] == product_id)
            if not row or row['base_grams'] is None:
                raise FarmError(f'“{name}”의 준비한 재고를 수량 화면에서 먼저 저장해 주세요.')
            sold = db.execute('SELECT COALESCE(SUM(grams),0) FROM sales WHERE product_id=?', (product_id,)).fetchone()[0]
            available = row['base_grams'] - sold + previous.get(product_id, 0)
            if grams > available:
                raise FarmError(f'“{name}” 재고가 부족해요. 반영 가능한 양: {kg(available)}kg. 메모와 재고는 바꾸지 않았어요.')
        now = datetime.now(timezone.utc).isoformat()
        db.execute('''INSERT INTO notes VALUES (?,?,?,?,?) ON CONFLICT(product_id,day)
            DO UPDATE SET body=excluded.body,version=excluded.version,updated_at=excluded.updated_at''', (pid, day, body, version + 1, now))
        db.execute('DELETE FROM sales WHERE source_product_id=? AND day=?', (pid, day))
        for product_id, grams in new_sales.items():
            db.execute('INSERT INTO sales VALUES (?,?,?,?)', (pid, day, product_id, grams))
        for product_id in set(previous) | set(new_sales):
            db.execute('UPDATE stock SET version=version+1 WHERE product_id=?', (product_id,))
    return True


def archive_product(path: Path, pid: str) -> None:
    with transaction(path) as db:
        db.execute('UPDATE products SET archived=1 WHERE id=?', (pid,))


def backup_json(path: Path) -> bytes:
    db = connect(path)
    try:
        db.execute('BEGIN')
        data = {table: [dict(r) for r in db.execute(f'SELECT * FROM {table}')] for table in ('products', 'stock', 'notes', 'sales')}
        db.commit()
    finally:
        db.close()
    return json.dumps({'format': 'dawon-farm-v1', 'exported_at': datetime.now(timezone.utc).isoformat(), 'data': data}, ensure_ascii=False, indent=2).encode('utf-8')


def emoji(name: str) -> str:
    for word, icon in [('딸기', '🍓'), ('상추', '🥬'), ('쪽파', '🌱'), ('토마토', '🍅'), ('당근', '🥕'), ('오이', '🥒'), ('사과', '🍎'), ('포도', '🍇'), ('고추', '🌶️')]:
        if word in name:
            return icon
    return '🌱'


def flash(message: str) -> None:
    st.session_state['flash'] = message
    st.rerun()


def pick_day(value: date) -> None:
    st.session_state['selected_day'] = value


def remember_note(widget: str, key: str) -> None:
    st.session_state['note_drafts'][key]['text'] = st.session_state[widget]


def remember_stock(widget: str, pid: str, version: int) -> None:
    st.session_state['stock_drafts'][pid] = {'text': st.session_state[widget], 'version': version}


def calendar_screen(path: Path, products: list[dict]) -> None:
    with st.container(key='product-panel'):
        st.subheader('판매하는 상품')
        if products:
            ids = [p['id'] for p in products]
            names = {p['id']: p['name'] for p in products}
            if st.session_state.get('selected_product') not in ids:
                st.session_state['selected_product'] = ids[0]
            with st.container(key='compact-product'):
                pid = st.selectbox('상품 선택', ids, format_func=lambda p: f'{emoji(names[p])} {names[p]}', key='selected_product')
        else:
            st.caption('첫 상품을 추가하고 판매를 기록해 보세요.')
        product_adder(path)
    with st.container(key='compact-date'):
        selected = st.date_input('기록할 날짜', key='selected_day', min_value=date(1900, 1, 1), max_value=date(2100, 12, 31), format='YYYY-MM-DD')
    with st.container(key='sale-calendar', border=True):
        st.subheader('판매 달력')
        draw_calendar(path, products, selected)
    if not products:
        st.text_area(f'{selected.month}월 {selected.day}일 메모', disabled=True, placeholder='상품을 추가하면 메모를 남길 수 있어요.')
        return
    memo_editor(path, products, pid, selected, names)


def draw_calendar(path: Path, products: list[dict], selected: date) -> None:
    year, month = selected.year, selected.month
    prev = date(year - (month == 1), 12 if month == 1 else month - 1, 1) if (year, month) > (1900, 1) else selected
    nxt = date(year + (month == 12), 1 if month == 12 else month + 1, 1) if (year, month) < (2100, 12) else selected
    with st.container(key='calendar-heading'):
        left, center, right = st.columns([1, 4, 1], gap='small')
        left.button('이전', help='이전 달', on_click=pick_day, args=(prev,), disabled=(year, month) == (1900, 1), use_container_width=True)
        center.markdown(f'<p class="calendar-month">{year}년 {month}월</p>', unsafe_allow_html=True)
        right.button('다음', help='다음 달', on_click=pick_day, args=(nxt,), disabled=(year, month) == (2100, 12), use_container_width=True)
    prefix = f'{year:04d}-{month:02d}'
    pid = st.session_state.get('selected_product')
    marked = {r['day'] for r in query(path, "SELECT day FROM notes WHERE product_id=? AND day LIKE ? AND TRIM(body)<>''", (pid, prefix + '%'))} if products else set()
    for column, label in zip(st.columns(7, gap='small'), ['일', '월', '화', '수', '목', '금', '토']):
        column.markdown(f'<p class="weekday">{label}</p>', unsafe_allow_html=True)
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        for column, number in zip(st.columns(7, gap='small'), week):
            if number:
                day = date(year, month, number)
                label = str(number) + (' ·' if day.isoformat() in marked else '')
                column.button(label, key=f'day-{day}', on_click=pick_day, args=(day,), type='primary' if day == selected else 'secondary', use_container_width=True)
    st.caption('· 표시: 저장된 메모가 있는 날이에요.')
    st.button('오늘 날짜로', on_click=pick_day, args=(date.today(),))


def memo_editor(path: Path, products: list[dict], pid: str, selected: date, names: dict) -> None:
    day = selected.isoformat()
    key = f'{pid}:{day}'
    saved_rows = query(path, 'SELECT * FROM notes WHERE product_id=? AND day=?', (pid, day))
    saved = saved_rows[0] if saved_rows else {'body': '', 'version': 0}
    drafts = st.session_state['note_drafts']
    if key not in drafts:
        drafts[key] = {'text': saved['body'], 'version': saved['version']}
    draft = drafts[key]
    widget = 'note-editor-' + key
    if widget not in st.session_state:
        st.session_state[widget] = draft['text']
    st.text_area(f'{selected.month}월 {selected.day}일 메모', key=widget, height=150, max_chars=3000, on_change=remember_note, args=(widget, key), placeholder='예시: 2kg 또는 딸기 2kg, 상추 500g')
    try:
        preview = parse_sales(draft['text'], products, pid)
        if preview:
            st.markdown('**저장하면 반영할 판매량**')
            for product_id, grams in preview.items():
                st.write(f'{names[product_id]}: {kg(grams)}kg')
        else:
            st.caption('판매량 없는 메모는 재고를 바꾸지 않아요. 빈 메모 저장은 기존 차감을 되돌려요.')
    except FarmError as error:
        st.warning(str(error))
    st.caption('저장하지 않은 변경이 있어요.' if draft['text'] != saved['body'] else '저장된 내용과 같아요.')
    if st.button('메모 저장', type='primary', use_container_width=True):
        try:
            changed = save_note(path, pid, day, draft['text'], draft['version'])
            del drafts[key]
            flash('메모를 저장하고 재고에 반영했어요.' if changed else '같은 내용이에요. 재고를 다시 차감하지 않았어요.')
        except (FarmError, sqlite3.Error) as error:
            st.error(str(error) if isinstance(error, FarmError) else '저장하지 못했어요. 다른 창의 작업이 끝나면 다시 시도해 주세요.')
    if st.button('이 메모 초안을 버리고 저장 기록 불러오기'):
        st.session_state['reload_note'] = key
        st.rerun()
    deductions = query(path, 'SELECT p.name,s.grams FROM sales s JOIN products p ON p.id=s.product_id WHERE source_product_id=? AND day=?', (pid, day))
    if deductions:
        st.markdown('**이 메모에 반영된 판매**')
        for row in deductions:
            st.write(f"{row['name']}: −{kg(row['grams'])}kg")


def quantity_screen(path: Path) -> None:
    view = st.radio('수량 보기', ['전체 재고', '월별 판매'], horizontal=True)
    rows = stock_rows(path)
    if view == '월별 판매':
        month_day = st.date_input('집계할 달의 날짜', value=date.today(), key='monthly-date')
        prefix = month_day.strftime('%Y-%m')
        monthly = query(path, '''SELECT p.id,p.name,p.archived,SUM(s.grams) grams FROM sales s
            JOIN products p ON p.id=s.product_id WHERE s.day LIKE ? GROUP BY p.id ORDER BY grams DESC,p.name''', (prefix + '%',))
        st.subheader(f'{month_day.year}년 {month_day.month}월 판매')
        st.metric('전체 판매량', kg(sum(r['grams'] for r in monthly)) + 'kg')
        if not monthly:
            st.info('이달에 저장한 판매 기록이 없어요.')
        stock = {r['id']: r for r in rows}
        for row in monthly:
            st.markdown(f"**{html.escape(row['name'])}{' (보관 상품)' if row['archived'] else ''}** · {kg(row['grams'])}kg")
            base = stock.get(row['id'], {}).get('base_grams')
            if base:
                ratio = row['grams'] / base
                st.progress(min(ratio, 1.0))
                st.caption(f'현재 준비한 재고 {kg(base)}kg 대비 {ratio:.1%} · 남은 재고 비율이 아니에요.')
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['월', '상품', '판매량(kg)', '보관 상품'])
        for row in monthly:
            name = row['name']
            if name.startswith(('=', '+', '-', '@', '\t', '\r')):
                name = "'" + name
            writer.writerow([prefix, name, str(Decimal(row['grams']) / 1000), '예' if row['archived'] else '아니오'])
        st.download_button('월별 판매 내려받기', output.getvalue().encode('utf-8-sig'), f'판매-{prefix}.csv', 'text/csv')
        return
    st.subheader('kg 재고 관리')
    st.caption('입고할 때는 기존 준비한 재고에 입고량을 더해 주세요. 날짜와 무관한 전체 재고예요.')
    if not rows:
        st.info('아래의 상품 관리에서 먼저 상품을 추가해 주세요.')
        return
    drafts = st.session_state['stock_drafts']
    for row in rows:
        pid = row['id']
        with st.container(border=True):
            st.markdown(f"### {emoji(row['name'])} {html.escape(row['name'])}")
            col1, col2 = st.columns(2)
            col1.metric('판매량', kg(row['sold_grams']) + 'kg')
            col2.metric('남은 재고', '미입력' if row['base_grams'] is None else kg(row['base_grams'] - row['sold_grams']) + 'kg')
            widget = 'stock-editor-' + pid
            initial = '' if row['base_grams'] is None else str(Decimal(row['base_grams']) / 1000)
            if widget not in st.session_state:
                st.session_state[widget] = drafts.get(pid, {}).get('text', initial)
            version = drafts.get(pid, {}).get('version', row['version'])
            st.text_input('준비한 재고 (kg)', key=widget, on_change=remember_stock, args=(widget, pid, version), placeholder='예시: 10.5')
    if st.button('재고 저장', type='primary', use_container_width=True):
        try:
            if not drafts:
                raise FarmError('재고를 입력하거나 바꾼 뒤 저장해 주세요.')
            save_stock(path, drafts)
            st.session_state['stock_drafts'] = {}
            flash('준비한 재고를 저장했어요.')
        except (FarmError, sqlite3.Error) as error:
            st.error(str(error) if isinstance(error, FarmError) else '재고를 저장하지 못했어요. 입력은 유지했어요.')
    st.caption('다른 창에서 변경돼 저장이 막히면 입력을 복사한 뒤 아래 버튼을 사용해 주세요.')
    if st.button('재고 초안을 버리고 저장 기록 불러오기'):
        st.session_state['reload_stock'] = True
        st.rerun()


def product_adder(path: Path) -> None:
    if st.button('＋ 상품 추가', key='show-add-product', use_container_width=True):
        st.session_state['show_product_form'] = not st.session_state.get('show_product_form', False)
    if st.session_state.get('show_product_form'):
        with st.form('add-products', clear_on_submit=False):
            names = st.text_area('추가할 상품 이름', placeholder='예시: 딸기\n상추\n쪽파', key='new-names')
            if st.form_submit_button('상품 추가'):
                try:
                    add_products(path, names)
                    st.session_state['clear_names'] = True
                    st.session_state['show_product_form'] = False
                    flash('상품을 추가했어요. 달력과 수량에 함께 표시돼요.')
                except FarmError as error:
                    st.error(str(error))


def management(path: Path, products: list[dict]) -> None:
    with st.expander('상품 삭제·기록 보관'):
        if products:
            labels = {p['id']: p['name'] for p in products}
            pid = st.selectbox('목록에서 삭제할 상품', list(labels), format_func=labels.get)
            confirmed = st.checkbox('이 상품을 두 화면에서 숨겨요. 기존 메모·판매·재고는 보관된다는 것을 확인했어요.', key='archive-confirm-' + pid)
            if st.button('선택 상품 삭제', disabled=not confirmed):
                archive_product(path, pid)
                st.session_state['stock_drafts'].pop(pid, None)
                st.session_state['note_drafts'] = {k: v for k, v in st.session_state['note_drafts'].items() if not k.startswith(pid + ':')}
                flash('상품을 목록에서 삭제했어요. 기존 기록은 보관했어요.')


def main() -> None:
    st.set_page_config(page_title='다원 딸기 농장', page_icon='🍓', layout='centered')
    st.markdown('''<style>
    /* Do not target generated st-* classes: they also include icon-font spans. */
    html,body,.stApp {font-family: Pretendard,-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;word-break:keep-all;}
    .stApp {background:#f5e9ec;color:#38272c;}
    .block-container {max-width:480px;padding:24px 20px 140px;margin:0 auto;}
    [data-testid="stHeader"] {background:transparent;}
    .stApp h1:not(.welcome-title) {font-size:25px;text-align:center;letter-spacing:-.02em;}
    .stApp h2,.stApp h3 {font-size:20px;letter-spacing:-.02em;}
    .st-key-compact-product {max-width:220px;}
    .st-key-compact-date {max-width:210px;}
    .st-key-sale-calendar {background:#fff!important;border:1px solid #f0dfe4!important;border-radius:24px!important;padding:20px 14px!important;}
    .st-key-sale-calendar [data-testid="stHorizontalBlock"] {flex-wrap:nowrap!important;gap:4px!important;}
    .st-key-sale-calendar [data-testid="stColumn"] {min-width:0!important;flex:1 1 0!important;}
    .st-key-calendar-heading [data-testid="stColumn"]:nth-child(2) {flex-grow:4!important;}
    .st-key-sale-calendar button {padding:0!important;min-height:42px;border-radius:13px;border-color:transparent;background:#fff;}
    .st-key-sale-calendar button[kind="primary"] {background:#cf3652;color:#fff;}
    .st-key-sale-calendar button p {white-space:nowrap;font-size:14px;}
    .calendar-month {text-align:center;font-weight:700;margin:8px 0!important;}
    .weekday {text-align:center;color:#75535e;font-size:13px;margin:4px 0!important;}
    .st-key-product-panel {padding-bottom:8px;}
    .st-key-show-add-product button {border:1px dashed #ce8c9c;background:#fff7f9;color:#93334c;min-height:44px;}
    .st-key-bottom-nav {position:fixed;bottom:0;left:50%;transform:translateX(-50%);width:min(100%,480px);z-index:999;background:#fffcfd;border:1px solid #ecdbe0;border-radius:24px 24px 0 0;padding:12px 20px max(14px,env(safe-area-inset-bottom));box-sizing:border-box;box-shadow:0 -5px 22px #5b20300a;}
    .st-key-bottom-nav [role="radiogroup"] {display:flex;gap:12px;width:100%;}
    .st-key-bottom-nav [data-testid="stElementContainer"] {width:100%;}
    .st-key-bottom-nav [role="radiogroup"]>div {flex:1;}
    .st-key-bottom-nav [role="radiogroup"] label {flex:1;display:flex;justify-content:center;min-height:56px;border-radius:16px;margin:0!important;color:#74545f;}
    .st-key-bottom-nav [role="radiogroup"] label:has(input:checked) {background:#fbe7ed;color:#9c2344;}
    .st-key-bottom-nav [role="radiogroup"] label>div>div:first-child {display:none;}
    .st-key-bottom-nav label:has(input:focus-visible) {outline:3px solid #b92749;outline-offset:2px;}
    .st-key-bottom-nav label p {font-size:15px;font-weight:650;}
    .st-key-bottom-nav [role="radiogroup"]>div:nth-child(1) p:before {content:'▦';display:block;text-align:center;font-size:23px;line-height:1.2;}
    .st-key-bottom-nav [role="radiogroup"]>div:nth-child(2) p:before {content:'▤';display:block;text-align:center;font-size:23px;line-height:1.2;}
    .stApp button,.st-key-bottom-nav label {touch-action:manipulation;}
    .stApp button:hover {filter:brightness(.97);}
    .stApp input,.stApp textarea,.stApp button {scroll-margin-bottom:120px;}
    h1,h2,h3 {color:#38272c;} p {line-height:1.8;}
    .stApp h1 {font-size:clamp(1.45rem,5vw,2.5rem);line-height:1.3;word-break:keep-all;overflow-wrap:normal;}
    .stApp p,.stApp h2,.stApp h3 {word-break:keep-all;overflow-wrap:break-word;}
    div[data-testid="stVerticalBlockBorderWrapper"] {background:#fffafa;border-radius:18px;}
    button[kind="primary"],button[kind="primaryFormSubmit"] {background:#cf3652;border-color:#cf3652;color:white;}
    button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible {outline:3px solid #b92749!important;outline-offset:3px;}
    [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;}
    .st-key-welcome-card {box-sizing:border-box;max-width:440px;margin:0 auto;padding:28px 32px 24px;border:1px solid #fff;border-radius:36px;background:#fffafa;}
    .welcome-brand {display:flex;align-items:center;justify-content:space-between;color:#80636d;font-size:12px;}
    .welcome-dot {width:8px;height:8px;border-radius:50%;background:#68816b;}
    .welcome-hero {display:flex;min-height:565px;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:34px 0;}
    .welcome-logo {display:flex;width:176px;height:176px;flex-shrink:0;align-items:center;justify-content:center;border:1px solid #f3dce1;border-radius:50%;background:#fceef1;margin-bottom:38px;}
    .welcome-logo svg {width:120px;height:120px;}
    .stApp .welcome-eyebrow {font-size:13px;color:#80636d;margin:0 0 12px;}
    .stApp .welcome-title {font-size:30px;font-weight:750;line-height:1.4;padding:0;margin:0;letter-spacing:-.02em;}
    .stApp .welcome-description {font-size:14px;color:#856c73;margin:20px 0 0;line-height:1.9;}
    .stApp .welcome-footer {text-align:center;font-size:12px;color:#80636d;margin:18px 0 0;}
    .st-key-welcome-card button {min-height:56px;border-radius:15px;font-weight:650;}
    @media(max-width:480px) {
      .block-container:has(.st-key-welcome-card) {padding:14px 16px 24px;}
      .st-key-welcome-card {padding:26px 26px 22px;border-radius:32px;}
      .welcome-hero {min-height:490px;}
      .welcome-logo {width:160px;height:160px;}
      .welcome-logo svg {width:112px;height:112px;}
      .stApp .welcome-title {font-size:27px;}
    }
    </style>''', unsafe_allow_html=True)
    root = Path(os.environ.get('APP_DATA_DIR', str(Path.home() / '.dawon-farm'))).expanduser()
    path = root / 'farm.sqlite3'
    try:
        initialize(path)
    except (OSError, sqlite3.Error):
        st.error('보관 폴더를 열지 못했어요. 컴퓨터의 저장 공간과 폴더 쓰기 권한을 확인해 주세요.')
        st.stop()
    st.session_state.setdefault('selected_day', date.today())
    st.session_state.setdefault('note_drafts', {})
    st.session_state.setdefault('stock_drafts', {})
    if st.session_state.pop('clear_names', False):
        st.session_state.pop('new-names', None)
    reload_note = st.session_state.pop('reload_note', None)
    if reload_note:
        st.session_state['note_drafts'].pop(reload_note, None)
        st.session_state.pop('note-editor-' + reload_note, None)
    if st.session_state.pop('reload_stock', False):
        st.session_state['stock_drafts'] = {}
        for key in list(st.session_state):
            if key.startswith('stock-editor-'):
                del st.session_state[key]
    st.session_state.setdefault('menu', '첫 화면')
    if st.session_state['menu'] == '첫 화면':
        def start():
            st.session_state['menu'] = '달력'
        with st.container(key='welcome-card'):
            st.markdown('''<div class="welcome-brand"><span>다원 딸기 농장</span><span class="welcome-dot" aria-hidden="true"></span></div>
<div class="welcome-hero">
  <div class="welcome-logo"><svg viewBox="0 0 120 120" role="img" aria-label="딸기 로고"><path d="M25 43C38 16 79 7 96 35C104 48 106 72 113 92C117 109 103 117 89 113L37 101C13 95 9 66 25 43Z" fill="#ff3b18" stroke="#080b05" stroke-width="7" stroke-linejoin="round"/><path d="M9 58C8 44 19 37 23 38V23H39C40 12 48 8 59 9V31H76C76 43 64 45 47 43V60L33 70V46H26V58Z" fill="#087b12" stroke="#080b05" stroke-width="7"/><g stroke="#bc1d1a" stroke-width="7" stroke-linecap="round"><path d="M70 48l3 3M91 48l3 3M49 69l3 3M70 69l3 3M91 69l3 3M49 90l3 3M70 90l3 3M91 90l3 3"/></g></svg></div>
  <p class="welcome-eyebrow">달콤한 하루의 시작</p>
  <h1 class="welcome-title">다원 딸기 농장</h1>
  <p class="welcome-description">오늘의 판매부터 하루의 기록까지<br>한곳에서 차근차근 관리해요.</p>
</div>''', unsafe_allow_html=True)
            st.button('판매 시작 ↗', type='primary', on_click=start, use_container_width=True)
            st.markdown('<p class="welcome-footer">정성으로 키우고, 차곡차곡 기록해요.</p>', unsafe_allow_html=True)
        return
    st.title('다원 딸기 농장')
    st.caption('정성으로 키우고, 차곡차곡 기록해요.')
    if 'flash' in st.session_state:
        st.success(st.session_state.pop('flash'))
    with st.container(key='bottom-nav'):
        menu = st.radio('판매 관리 메뉴', ['달력', '수량'], horizontal=True, key='menu', label_visibility='collapsed')
    products = all_products(path)
    try:
        if menu == '달력':
            calendar_screen(path, products)
        elif menu == '수량':
            quantity_screen(path)
            product_adder(path)
        management(path, products)
        with st.expander('기록 보관·백업 안내'):
            st.write('메모·재고 저장을 누른 기록은 창을 닫아도 같은 컴퓨터에 남아요. 저장 전 초안은 새로고침하면 사라질 수 있어요.')
            st.code(str(path), language=None)
            st.write('컴퓨터를 바꾸려면 앱을 모두 종료한 뒤 .dawon-farm 폴더 전체를 복사해 새 컴퓨터의 같은 사용자 폴더 아래에 넣어 주세요. 실행 중인 파일 하나만 복사하면 최근 기록이 빠질 수 있어요.')
            st.download_button('전체 기록 JSON 내려받기', backup_json(path), f'다원농장-백업-{date.today().isoformat()}.json', 'application/json')
            st.caption('JSON은 열람·외부 보관용이에요. 이 앱에서 JSON을 다시 올리는 기능은 없어요. 컴퓨터 이전에는 폴더 전체를 복사해 주세요. 기존 BAZE 기록은 자동 이전하지 않아요.')
    except sqlite3.Error:
        st.error('기록을 읽지 못했어요. 다른 창의 작업이 끝난 뒤 다시 시도해 주세요. 보관 폴더를 삭제하지 마세요.')
    st.caption('주소지·지도·AI 연결 없는 개인 컴퓨터용 버전이에요. 인터넷에 공개하면 다른 사람도 기록을 바꿀 수 있으니 공개하지 마세요.')


if __name__ == '__main__':
    main()
