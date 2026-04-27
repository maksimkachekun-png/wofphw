import sqlite3, json, threading, time, re
from datetime import datetime, timedelta
import telebot
from telebot import types

token = ""
channel_id = 
channel_link = ""
admin = 
payment = 4.0
hold = 5 * 60
timeout_phone = 60
timeout_kod = 3 * 60
timeout_pwd = 3 * 60
queue_timeout = 10 * 60
activity_timeout = 3 * 60
activity_confirm = 2 * 60
min_withdraw = 30.0

group = []
vyvod_channel = ""
vyvod_channel_id = 
support = ""

local = threading.local()

def db():
    if not hasattr(local, "conn"):
        local.conn = sqlite3.connect("baza.db", check_same_thread=False)
        local.conn.row_factory = sqlite3.Row
    return local.conn

def setup():
    c = db().cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            bal REAL DEFAULT 0.0,
            role TEXT DEFAULT 'drop',
            state TEXT,
            temp TEXT,
            total_orders INTEGER DEFAULT 0,
            total_earned REAL DEFAULT 0.0,
            today_earned REAL DEFAULT 0.0,
            last_earning_date TEXT,
            sub INTEGER DEFAULT 0,
            blocked INTEGER DEFAULT 0,
            pending_withdraw REAL DEFAULT 0.0,
            in_queue INTEGER DEFAULT 0,
            queue_msg_id INTEGER,
            activity_msg_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cold_id INTEGER,
            drop_id INTEGER,
            phone TEXT,
            kod TEXT,
            pwd TEXT,
            status TEXT DEFAULT 'wait_drop',
            msg_grp INTEGER,
            msg_thread_id INTEGER,
            msg_kanal INTEGER,
            msg_drop INTEGER,
            hold_until TEXT,
            paid INTEGER DEFAULT 0,
            created TEXT,
            group_id INTEGER,
            queue_position INTEGER DEFAULT 0,
            grp_msg_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS vyvod (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            summa REAL,
            status TEXT DEFAULT 'wait',
            created TEXT,
            admin_msg_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    try:
        c.execute("ALTER TABLE users ADD COLUMN sub INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN pending_withdraw REAL DEFAULT 0.0")
    except: pass
    try:
        c.execute("ALTER TABLE vyvod ADD COLUMN admin_msg_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN msg_thread_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN pwd TEXT")
    except: pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN group_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN in_queue INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN queue_msg_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN activity_msg_id INTEGER")
    except: pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN queue_position INTEGER DEFAULT 0")
    except: pass
    try:
        c.execute("ALTER TABLE orders ADD COLUMN grp_msg_id INTEGER")
    except: pass
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('price', ?)", (str(payment),))
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('accept', 'on')")
    db().commit()

setup()
bot = telebot.TeleBot(token, parse_mode="HTML")

def get_price():
    c = db().cursor()
    c.execute("SELECT value FROM settings WHERE key='price'")
    r = c.fetchone()
    return float(r['value']) if r else payment

def is_accepting():
    c = db().cursor()
    c.execute("SELECT value FROM settings WHERE key='accept'")
    r = c.fetchone()
    return r['value'] == 'on' if r else True

def fmt(n):
    if n is None: return "0"
    return str(int(n)) if n == int(n) else f"{n:.2f}"

def mask_username(un):
    if not un: return "Пользователь"
    if len(un) <= 4: return f"@{un}"
    return f"@{un[:4]}***"

def prof(u):
    return (
        f"> 👤 *Ваш ID:* `{u['id']}`\n"
        f"> 💳 *Баланс:* `{fmt((u['bal'] or 0) - (u['pending_withdraw'] or 0))}$`\n\n"
        f"> — *📊 Статистика:*\n"
        f"> 💰 *Сегодня:* `{fmt(u['today_earned'] or 0)}$`\n"
        f"> 📦 *Сдано номеров:* `{u['total_orders'] or 0}`\n"
        f"> 💵 *Всего оплачено:* `{fmt(u['total_earned'] or 0)}$`"
    )

def prof_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💸 Вывод", callback_data="vyvod_n"),
           types.InlineKeyboardButton("🔙 Назад", callback_data="back_start"))
    return kb

def start_text(uid=None):
    pr = get_price()
    if uid:
        u = get_u(uid)
        if u and u['username']:
            name = f"Привет, @{u['username']}\\!"
        else:
            name = "Добро пожаловать\\!"
    else:
        name = "Добро пожаловать\\!"
    return (
        f">{name}\n"
        f">Это бот по приёму аккаунтов MAX, мы берём любые номера РФ рег или нерег\\!\n"
        f">Прайс за номер \\- `{int(pr)}$`\n"
        f">\n"
        f">*Выбери дальнейшее действие:*"
    )

def start_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📞 Добавить номер", callback_data="add_num"))
    kb.add(types.InlineKeyboardButton("👤 Профиль", callback_data="show_prof"),
           types.InlineKeyboardButton("👨‍💻 Техподдержка", callback_data="help"))
    kb.add(types.InlineKeyboardButton("💬 Канал с выводами", url=vyvod_channel))
    return kb

def support_text():
    return (
        "> 👨‍💻 *Техподдержка*\n"
        "> \n"
        "> Если у вас возникли проблемы или вопросы, пишите:\n"
        f"> {support}\n"
        "> \n"
        "> _Опишите вашу проблему и вам помогут в ближайшее время_"
    )

def support_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_start"))
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_start"))
    return kb

def hide_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Скрыть", callback_data="hide_msg"))
    return kb

def confirm_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("✅ Да", callback_data="confirm_yes"),
           types.InlineKeyboardButton("❌ Я передумал", callback_data="back_start"))
    return kb

def activity_kb(oid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⏳ Подтвердить активность", callback_data=f"keep_{oid}"))
    return kb

def adm_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Изменить цену", callback_data="adm_prc"),
           types.InlineKeyboardButton("Изменить баланс", callback_data="adm_bal"),
           types.InlineKeyboardButton("Рассылка", callback_data="adm_snd"),
           types.InlineKeyboardButton("Заблокировать", callback_data="adm_blk"),
           types.InlineKeyboardButton("Разблокировать", callback_data="adm_ublk"),
           types.InlineKeyboardButton("Вкл/Выкл приём", callback_data="adm_accept"),
           types.InlineKeyboardButton("Закрыть", callback_data="adm_cls"))
    return kb

def sub_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Подписаться", url=channel_link),
           types.InlineKeyboardButton("Проверить подписку", callback_data="chk_sub"))
    return kb

def check_phone(p):
    p = re.sub(r'[\s\-\(\)]', '', p)
    if p.startswith('+7') and len(p) == 12 and p[1:].isdigit(): return True, p
    if len(p) == 11 and p.isdigit() and p[0] in ['7','8']:
        if p[0] == '8': p = '+7' + p[1:]
        else: p = '+' + p
        return True, p
    return False, None

def check_kod(k):
    return len(k) == 6 and k.isdigit()

def check_subscription(uid):
    try:
        member = bot.get_chat_member(channel_id, uid)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

def is_blocked(uid):
    u = get_u(uid)
    return u and u['blocked'] == 1

def get_available_balance(uid):
    u = get_u(uid)
    if not u: return 0
    return (u['bal'] or 0) - (u['pending_withdraw'] or 0)

def get_queue_position(uid):
    c = db().cursor()
    c.execute("SELECT COUNT(*) as cnt FROM orders WHERE status='in_queue' AND id < (SELECT MIN(id) FROM orders WHERE drop_id=? AND status='in_queue')", (uid,))
    r = c.fetchone()
    return (r['cnt'] or 0) + 1

def update_queue_positions():
    c = db().cursor()
    c.execute("SELECT id FROM orders WHERE status='in_queue' ORDER BY id")
    orders = c.fetchall()
    for i, o in enumerate(orders):
        c.execute("UPDATE orders SET queue_position=? WHERE id=?", (i+1, o['id']))
    db().commit()

def notify_queue_users():
    c = db().cursor()
    c.execute("SELECT o.id, o.drop_id, o.phone FROM orders o WHERE o.status='in_queue' ORDER BY o.id")
    orders = c.fetchall()
    for i, o in enumerate(orders):
        pos = i + 1
        u = get_u(o['drop_id'])
        if u and u['queue_msg_id']:
            try:
                txt = f"> ✅ *Номер `{o['phone']}` принят\\!*\n> \n> ⏳ *Ожидайте запроса кода\\.*\n> \n> — _Код должен состоять из 6 цифр\\. Ввод неверных данных карается баном\\._\n> \n> _Если номер не примут в течение 3 минут, появится кнопка продления\\._"
                bot.edit_message_text(txt, o['drop_id'], u['queue_msg_id'], parse_mode="MarkdownV2")
            except:
                pass

def worker():
    while True:
        try:
            time.sleep(5)
            c = db().cursor()
            now = datetime.now()
            today = now.date().isoformat()
            pr = get_price()
            c.execute("""
                SELECT o.id, o.drop_id, o.phone, u.last_earning_date, u.bal
                FROM orders o JOIN users u ON o.drop_id = u.id
                WHERE o.status='done' AND o.paid=0 AND o.hold_until <= ?
            """, (now.isoformat(),))
            for r in c.fetchall():
                oid, drop, ph, ld, old = r['id'], r['drop_id'], r['phone'], r['last_earning_date'], r['bal'] or 0
                c.execute("UPDATE users SET bal = bal + ? WHERE id=?", (pr, drop))
                if ld != today:
                    c.execute("UPDATE users SET total_orders=total_orders+1, total_earned=total_earned+?, today_earned=?, last_earning_date=? WHERE id=?", (pr, pr, today, drop))
                else:
                    c.execute("UPDATE users SET total_orders=total_orders+1, total_earned=total_earned+?, today_earned=today_earned+? WHERE id=?", (pr, pr, drop))
                c.execute("UPDATE orders SET paid=1 WHERE id=?", (oid,))
                db().commit()
                try:
                    txt = f"> 💸 *Начисление\\!*\n> Номер `{ph}` успешно встал\n> *На ваш баланс было начислено:* `{int(pr)}$`\n> *Текущий баланс:* `{fmt(old+pr)}$`"
                    bot.send_message(drop, txt, parse_mode="MarkdownV2", reply_markup=hide_kb())
                except: pass
        except Exception as e: print(e); time.sleep(5)
threading.Thread(target=worker, daemon=True).start()

def activity_checker(oid, uid, mid):
    while True:
        time.sleep(activity_timeout)
        try:
            o = get_o(oid)
            if not o or o['status'] != 'in_queue':
                break
            
            msg = bot.send_message(
                uid,
                f"> ⚠️ *Внимание\\!*\n> Ваш номер `{o['phone']}` всё ещё в очереди\\.\n> Позиция: *{get_queue_position(uid)}*\n> \n> _У вас есть 2 минуты чтобы нажать кнопку ниже и продлить номер в очереди, иначе он будет удалён\\._",
                parse_mode="MarkdownV2",
                reply_markup=activity_kb(oid)
            )
            cur = db().cursor()
            cur.execute("UPDATE users SET activity_msg_id=? WHERE id=?", (msg.message_id, uid))
            db().commit()
            
            time.sleep(activity_confirm)
            
            u = get_u(uid)
            if u and u['activity_msg_id'] is None:
                try:
                    bot.delete_message(uid, msg.message_id)
                except:
                    pass
                continue
            
            o2 = get_o(oid)
            if o2 and o2['status'] == 'in_queue':
                cur = db().cursor()
                cur.execute("UPDATE orders SET status='cancel' WHERE id=?", (oid,))
                cur.execute("UPDATE users SET in_queue=0, queue_msg_id=NULL, activity_msg_id=NULL WHERE id=?", (uid,))
                db().commit()
                update_queue_positions()
                notify_queue_users()               
                try:
                    bot.delete_message(uid, mid)
                except:
                    pass
                try:
                    bot.send_message(uid, "> ❌ *Время вышло\\.*\n> Ваш номер удалён из очереди\\.", parse_mode="MarkdownV2")
                except:
                    pass
                try:
                    bot.delete_message(uid, msg.message_id)
                except:
                    pass
            break
        except:
            break

def add_u(uid, n, un):
    c = db().cursor()
    c.execute("INSERT OR IGNORE INTO users (id, name, username) VALUES (?, ?, ?)", (uid, n, un))
    db().commit()

def get_u(uid):
    c = db().cursor()
    c.execute("SELECT * FROM users WHERE id=?", (uid,))
    return c.fetchone()

def set_st(uid, s, t=None):
    c = db().cursor()
    c.execute("UPDATE users SET state=?, temp=? WHERE id=?", (s, t, uid))
    db().commit()

def get_o(oid):
    c = db().cursor()
    c.execute("SELECT * FROM orders WHERE id=?", (oid,))
    return c.fetchone()

def upd_o(oid, **kw):
    c = db().cursor()
    f = ", ".join([f"{k}=?" for k in kw])
    v = list(kw.values()) + [oid]
    c.execute(f"UPDATE orders SET {f} WHERE id=?", v)
    db().commit()

def get_next_in_queue():
    c = db().cursor()
    c.execute("SELECT * FROM orders WHERE status='in_queue' ORDER BY id LIMIT 1")
    return c.fetchone()

def process_queue_for_cold(cold_id, thread_id, group_id):
    o = get_next_in_queue()
    if not o:
        bot.send_message(group_id, "❌ Очередь пуста. Нет доступных номеров.", message_thread_id=thread_id)
        return
    
    upd_o(o['id'], cold_id=cold_id, status='wait_kod', group_id=group_id, msg_thread_id=thread_id)
    c = db().cursor()
    c.execute("UPDATE users SET in_queue=0, queue_msg_id=NULL WHERE id=?", (o['drop_id'],))
    db().commit()
    update_queue_positions()
    notify_queue_users()
    
    drop = get_u(o['drop_id'])
    if drop['username']:
        uinf = f"@{drop['username']}"
    elif drop['name']:
        uinf = drop['name']
    else:
        uinf = "Пользователь"
    uinf += f" [<code>{o['drop_id']}</code>]"
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📲 Запросить код", callback_data=f"c_kod_{o['id']}"),
           types.InlineKeyboardButton("🔐 Установлен пароль", callback_data=f"c_pwd_{o['id']}"),
           types.InlineKeyboardButton("✅ Встал", callback_data=f"c_ok_{o['id']}"),
           types.InlineKeyboardButton("❌ Слетел", callback_data=f"c_no_{o['id']}"),
           types.InlineKeyboardButton("⏭ Пропустить", callback_data=f"c_skip_{o['id']}"))
    
    msg = bot.send_message(group_id, f"<b>📱 Заявка #{o['id']}</b>\n\n<b>{uinf}</b>\n<b>Номер:</b> <code>{o['phone']}</code>", reply_markup=kb, message_thread_id=thread_id)
    upd_o(o['id'], grp_msg_id=msg.message_id)
    bot.send_message(o['drop_id'], f"> ✅ Ваш номер взят в работу\\!\n> Ожидайте запрос кода\\.", parse_mode="MarkdownV2")

def request_code_from_drop(oid, drop_id, phone):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔢 Ввести код", callback_data=f"d_kod_{oid}"),
           types.InlineKeyboardButton("🔄 Запросить повтор", callback_data=f"d_rep_{oid}"))
    bot.send_message(drop_id, f"> ✍️ *Отправьте код для входа в аккаунт\\.*\n> \n> — _Код должен состоять из 6 цифр\\. Ввод неверных данных карается баном\\._", parse_mode="MarkdownV2", reply_markup=kb)

def request_pwd_from_drop(oid, drop_id, phone):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🔐 Ввести пароль", callback_data=f"d_pwd_{oid}"),
           types.InlineKeyboardButton("🔄 Запросить повтор", callback_data=f"d_rep_{oid}"))
    bot.send_message(drop_id, f"> 🔐 *Введите облачный пароль для номера* `{phone}`\n> \n> — _Пароль должен быть точным\\. Ввод неверных данных карается баном\\._", parse_mode="MarkdownV2", reply_markup=kb)

@bot.message_handler(commands=['admin'])
def adm_cmd(m):
    if m.from_user.id != admin: return
    status = "ВКЛ" if is_accepting() else "ВЫКЛ"
    bot.send_message(m.chat.id, f"*👑 Админ\\-панель*\n\nТекущая цена: `{get_price()}$`\nПриём номеров: *{status}*", parse_mode="MarkdownV2", reply_markup=adm_kb())

@bot.callback_query_handler(func=lambda c: c.data == "adm_cls")
def adm_close(c):
    if c.from_user.id != admin: return
    bot.delete_message(c.message.chat.id, c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_prc")
def adm_price(c):
    if c.from_user.id != admin: return
    bot.send_message(c.message.chat.id, "Введите новую цену за номер в $:")
    set_st(c.from_user.id, "adm_wait_price")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_bal")
def adm_balance(c):
    if c.from_user.id != admin: return
    bot.send_message(c.message.chat.id, "Введите ID пользователя и сумму через пробел\nПример: `123456789 10` — добавить 10$\n`123456789 -5` — забрать 5$", parse_mode="MarkdownV2")
    set_st(c.from_user.id, "adm_wait_balance")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_snd")
def adm_broadcast(c):
    if c.from_user.id != admin: return
    bot.send_message(c.message.chat.id, "Введите текст для рассылки:")
    set_st(c.from_user.id, "adm_wait_broadcast")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_blk")
def adm_block(c):
    if c.from_user.id != admin: return
    bot.send_message(c.message.chat.id, "Введите ID пользователя для блокировки:")
    set_st(c.from_user.id, "adm_wait_block")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_ublk")
def adm_unblock(c):
    if c.from_user.id != admin: return
    bot.send_message(c.message.chat.id, "Введите ID пользователя для разблокировки:")
    set_st(c.from_user.id, "adm_wait_unblock")
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "adm_accept")
def adm_accept(c):
    if c.from_user.id != admin: return
    cur = db().cursor()
    if is_accepting():
        cur.execute("UPDATE settings SET value='off' WHERE key='accept'")
        db().commit()
        bot.answer_callback_query(c.id, "🔴 Приём номеров выключен", show_alert=True)
    else:
        cur.execute("UPDATE settings SET value='on' WHERE key='accept'")
        db().commit()
        bot.answer_callback_query(c.id, "🟢 Приём номеров включен", show_alert=True)

@bot.message_handler(func=lambda m: m.from_user.id == admin and m.reply_to_message is not None)
def adm_reply(m):
    t = m.reply_to_message.text or ""
    if "Заявка на вывод #" not in t: return
    try: rid = int(t.split("#")[1].split("\n")[0])
    except: return
    c = db().cursor()
    c.execute("SELECT * FROM vyvod WHERE id=?", (rid,))
    r = c.fetchone()
    if not r or r['status'] != 'wait': bot.send_message(admin, "Заявка уже обработана"); return
    chk = m.text.strip()
    for x in ['_','*','[',']','(',')','~','`','>','#','+','-','=','|','{','}','.','!']: chk = chk.replace(x, f'\\{x}')
    txt = f"> 💳 *Чек на выплату:*\n> {chk}\n> \n> — 👨‍💻 *Спасибо за доверие к нашему сервису\\!*"
    bot.send_message(r['user_id'], txt, parse_mode="MarkdownV2")
    c.execute("UPDATE vyvod SET status='done' WHERE id=?", (rid,))
    c.execute("UPDATE users SET bal = bal - ?, pending_withdraw = pending_withdraw - ? WHERE id=?", (r['summa'], r['summa'], r['user_id']))
    db().commit()
    
    u = get_u(r['user_id'])
    masked = mask_username(u['username']) if u else "Пользователь"
    try:
        bot.send_message(vyvod_channel_id, f"<b>{masked} успешно вывел <code>{int(r['summa'])}$</code></b>", parse_mode="HTML")
    except:
        pass
    
    bot.send_message(admin, f"✅ Чек отправлен, заявка #{rid} выполнена")

@bot.callback_query_handler(func=lambda c: c.data == "chk_sub")
def check_sub_cb(c):
    uid = c.from_user.id
    if check_subscription(uid):
        cur = db().cursor()
        cur.execute("UPDATE users SET sub=1 WHERE id=?", (uid,))
        db().commit()
        try:
            bot.delete_message(uid, c.message.message_id)
        except:
            pass
        try:
            with open('max.jpg', 'rb') as photo:
                bot.send_photo(uid, photo, caption=start_text(uid), parse_mode="MarkdownV2", reply_markup=start_kb())
        except:
            bot.send_message(uid, start_text(uid), parse_mode="MarkdownV2", reply_markup=start_kb())
    else:
        bot.answer_callback_query(c.id, "Вы не подписались на канал!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "show_prof")
def cb_show_profile(c):
    uid = c.from_user.id
    u = get_u(uid)
    if not u: return
    if not check_subscription(uid):
        bot.answer_callback_query(c.id, "❌ Подпишитесь на канал!", show_alert=True)
        return
    try:
        bot.edit_message_caption(prof(u), uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=prof_kb())
    except:
        pass
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "help")
def cb_support(c):
    uid = c.from_user.id
    if not check_subscription(uid):
        bot.answer_callback_query(c.id, "❌ Подпишитесь на канал!", show_alert=True)
        return
    try:
        bot.edit_message_caption(support_text(), uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=support_kb())
    except:
        pass
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "add_num")
def cb_add_number(c):
    uid = c.from_user.id
    if not check_subscription(uid):
        bot.answer_callback_query(c.id, "❌ Подпишитесь на канал!", show_alert=True)
        return
    if is_blocked(uid):
        bot.answer_callback_query(c.id, "❌ Вы заблокированы", show_alert=True)
        return
    
    if not is_accepting():
        try:
            bot.edit_message_caption(
                "> 🚫 *Приём номеров завершён\\! Возвращайтесь позже\\!*\n> *В основном, приём номеров открывается утром\\.*",
                uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=back_kb()
            )
        except:
            pass
        bot.answer_callback_query(c.id)
        return
    
    u = get_u(uid)
    if u and u['in_queue'] == 1:
        bot.answer_callback_query(c.id, "❌ Вы уже в очереди!", show_alert=True)
        return
    
    try:
        bot.edit_message_caption(
            "> *Вы точно хотите сдать свой номер?*",
            uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=confirm_kb()
        )
    except:
        pass
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "confirm_yes")
def confirm_add(c):
    uid = c.from_user.id
    set_st(uid, "wait_phone_queue")
    try:
        bot.edit_message_caption(
            "> ✍️ *Отправьте номер телефона*\n> \n> — _Ввод неверных данных и нарушение правил сервиса караются баном\\._",
            uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=back_kb()
        )
    except:
        pass
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("keep_"))
def confirm_active(c):
    uid = c.from_user.id
    oid = int(c.data.split("_")[1])
    o = get_o(oid)
    if not o or o['drop_id'] != uid or o['status'] != 'in_queue':
        bot.answer_callback_query(c.id, "❌ Заявка не найдена", show_alert=True)
        return
    
    u = get_u(uid)
    if u and u['activity_msg_id']:
        try:
            bot.delete_message(uid, u['activity_msg_id'])
        except:
            pass
    
    if u and u['queue_msg_id']:
        try:
            bot.delete_message(uid, u['queue_msg_id'])
        except:
            pass
    
    txt = f"> ✅ *Номер `{o['phone']}` принят\\!*\n> \n> ⏳ *Ожидайте запроса кода\\.*\n> \n> — _Код должен состоять из 6 цифр\\. Ввод неверных данных карается баном\\._\n> \n> _Номер продлён\\. Если не примут, кнопка появится снова через 3 минуты\\._"
    msg = bot.send_message(uid, txt, parse_mode="MarkdownV2")
    
    cur = db().cursor()
    cur.execute("UPDATE users SET activity_msg_id=NULL, queue_msg_id=? WHERE id=?", (msg.message_id, uid))
    db().commit()
    
    bot.answer_callback_query(c.id, "✅ Номер продлён!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "back_start")
def back_to_start(c):
    uid = c.from_user.id
    set_st(uid, None)
    try:
        bot.edit_message_caption(start_text(uid), uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=start_kb())
    except:
        pass
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_prof")
def back_to_profile(c):
    uid = c.from_user.id
    u = get_u(uid)
    if not u: return
    set_st(uid, None)
    try:
        bot.edit_message_caption(prof(u), uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=prof_kb())
    except:
        pass
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("d_"))
def drop_acts(c):
    d = c.data.split("_")
    act, oid = d[1], int(d[2])
    o = get_o(oid)
    if not o or o['drop_id'] != c.from_user.id: bot.answer_callback_query(c.id, "❌ Не ваша заявка", show_alert=True); return
    
    if act == "kod":
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        set_st(c.from_user.id, "wait_drop_kod", str(oid))
        msg = bot.send_message(c.from_user.id, f"> ✍️ *Отправьте код для входа в аккаунт\\.*\n> \n> — _Код должен состоять из 6 цифр\\. Ввод неверных данных карается баном\\._", parse_mode="MarkdownV2")
        upd_o(oid, msg_drop=msg.message_id)
        bot.answer_callback_query(c.id)
        
    elif act == "rep":
        if o['group_id'] and o['grp_msg_id']:
            bot.send_message(o['group_id'], f"🔄 Дроп запросил повторную отправку кода для заявки #{oid}", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        bot.answer_callback_query(c.id, "✅ Запрос передан холодку", show_alert=True)
        
    elif act == "pwd":
        try: bot.delete_message(c.message.chat.id, c.message.message_id)
        except: pass
        set_st(c.from_user.id, "wait_drop_pwd", str(oid))
        msg = bot.send_message(c.from_user.id, f"> 🔐 *Введите облачный пароль для номера* `{o['phone']}`\n> \n> — _Пароль должен быть точным\\. Ввод неверных данных карается баном\\._", parse_mode="MarkdownV2")
        upd_o(oid, msg_drop=msg.message_id)
        bot.answer_callback_query(c.id)

@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    add_u(uid, m.from_user.full_name, m.from_user.username)
    if m.chat.id != uid: return
    
    if is_blocked(uid):
        bot.send_message(uid, "> ❌ *Вы заблокированы за нарушение правил бота\\.*", parse_mode="MarkdownV2")
        return
    
    if not check_subscription(uid):
        txt = "> *Перед тем как начать использовать бота, подпишитесь на канал с заявками\\!*"
        bot.send_message(uid, txt, parse_mode="MarkdownV2", reply_markup=sub_kb())
        return
    
    cur = db().cursor()
    cur.execute("UPDATE users SET sub=1 WHERE id=?", (uid,))
    db().commit()
    
    try:
        with open('max.jpg', 'rb') as photo:
            bot.send_photo(uid, photo, caption=start_text(uid), parse_mode="MarkdownV2", reply_markup=start_kb())
    except:
        bot.send_message(uid, start_text(uid), parse_mode="MarkdownV2", reply_markup=start_kb())

@bot.message_handler(func=lambda m: m.chat.id in group and m.text and m.text.lower() in ["номер", "number", "н"])
def get_number(m):
    process_queue_for_cold(m.from_user.id, m.message_thread_id, m.chat.id)

@bot.callback_query_handler(func=lambda c: c.data == "hide_msg")
def hide(c): bot.delete_message(c.message.chat.id, c.message.message_id); bot.answer_callback_query(c.id)

@bot.message_handler(func=lambda m: True, content_types=['text'])
def text_h(m):
    if m.chat.id in group:
        return
    
    uid = m.from_user.id
    u = get_u(uid)
    if not u and uid != admin: return
    
    if u and u['state'] == "wait_drop_kod":
        kod = m.text.strip()
        if not check_kod(kod):
            bot.send_message(uid, "> ❌ *Неверный формат кода\\!*\n> Код должен состоять из 6 цифр\\. Попробуйте ещё раз\\.", parse_mode="MarkdownV2")
            return
        oid = int(u['temp'])
        o = get_o(oid)
        if not o:
            bot.send_message(uid, "Заявка не найдена")
            set_st(uid, None)
            return
        cur = db().cursor()
        cur.execute("UPDATE orders SET kod=? WHERE id=?", (kod, oid))
        db().commit()
        
        bot.send_message(uid, "> *🔏 Подождите\\. Номер проходит проверку*\n> \n> — _Не забывайте что ввод неверных данных карается баном\\._", parse_mode="MarkdownV2")
        set_st(uid, None)
        
        if o['group_id'] and o['grp_msg_id']:
            drop = u
            if drop['username']:
                uinf = f"@{drop['username']}"
            elif drop['name']:
                uinf = drop['name']
            else:
                uinf = "Пользователь"
            uinf += f" [<code>{uid}</code>]"
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(types.InlineKeyboardButton("📲 Запросить код повторно", callback_data=f"c_kod_{oid}"),
                   types.InlineKeyboardButton("🔐 Установлен пароль", callback_data=f"c_pwd_{oid}"),
                   types.InlineKeyboardButton("✅ Встал", callback_data=f"c_ok_{oid}"),
                   types.InlineKeyboardButton("❌ Слетел", callback_data=f"c_no_{oid}"),
                   types.InlineKeyboardButton("⏭ Пропустить", callback_data=f"c_skip_{oid}"))
            try:
                bot.edit_message_text(
                    f"<b>📱 Заявка #{oid}</b>\n\n<b>{uinf}</b>\n<b>Номер:</b> <code>{o['phone']}</code>\n<b>Код:</b> <code>{kod}</code>",
                    o['group_id'], o['grp_msg_id'], reply_markup=kb, parse_mode="HTML"
                )
            except:
                pass
        return
    
    if u and u['state'] == "wait_drop_pwd":
        pwd = m.text.strip()
        oid = int(u['temp'])
        o = get_o(oid)
        if not o:
            bot.send_message(uid, "Заявка не найдена")
            set_st(uid, None)
            return
        cur = db().cursor()
        cur.execute("UPDATE orders SET pwd=? WHERE id=?", (pwd, oid))
        db().commit()
        
        bot.send_message(uid, "> *🔏 Пароль отправлен\\. Номер проходит проверку*\n> \n> — _Не забывайте что ввод неверных данных карается баном\\._", parse_mode="MarkdownV2")
        set_st(uid, None)
        
        if o['group_id'] and o['grp_msg_id']:
            drop = u
            if drop['username']:
                uinf = f"@{drop['username']}"
            elif drop['name']:
                uinf = drop['name']
            else:
                uinf = "Пользователь"
            uinf += f" [<code>{uid}</code>]"
            kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(types.InlineKeyboardButton("📲 Запросить пароль повторно", callback_data=f"c_pwd_{oid}"),
                   types.InlineKeyboardButton("✅ Встал", callback_data=f"c_ok_{oid}"),
                   types.InlineKeyboardButton("❌ Слетел", callback_data=f"c_no_{oid}"),
                   types.InlineKeyboardButton("⏭ Пропустить", callback_data=f"c_skip_{oid}"))
            try:
                bot.edit_message_text(
                    f"<b>📱 Заявка #{oid}</b>\n\n<b>{uinf}</b>\n<b>Номер:</b> <code>{o['phone']}</code>\n<b>Пароль:</b> <code>{pwd}</code>",
                    o['group_id'], o['grp_msg_id'], reply_markup=kb, parse_mode="HTML"
                )
            except:
                pass
        return
    
    if uid != admin and is_blocked(uid):
        bot.send_message(uid, "> ❌ *Вы заблокированы за нарушение правил бота\\.*", parse_mode="MarkdownV2")
        return
    
    if uid != admin and not check_subscription(uid):
        txt = "> *Перед тем как начать использовать бота, подпишитесь на канал с заявками\\!*"
        bot.send_message(uid, txt, parse_mode="MarkdownV2", reply_markup=sub_kb())
        return
    
    st = u['state'] if u else None

    if uid == admin:
        if st == "adm_wait_price":
            try:
                np = float(m.text.strip())
                if np <= 0: raise
            except: bot.send_message(uid, "❌ Введите положительное число"); return
            cur = db().cursor()
            cur.execute("UPDATE settings SET value=? WHERE key='price'", (str(np),))
            db().commit()
            bot.send_message(uid, f"✅ Цена изменена на {np}$")
            set_st(uid, None); return
        if st == "adm_wait_balance":
            p = m.text.strip().split()
            if len(p) != 2: bot.send_message(uid, "❌ Неверный формат. Пример: `123456789 10`"); return
            try:
                tid = int(p[0])
                amt = float(p[1])
            except: bot.send_message(uid, "❌ Неверные числа"); return
            tgt = get_u(tid)
            if not tgt: bot.send_message(uid, "❌ Пользователь не найден"); return
            cur = db().cursor()
            cur.execute("UPDATE users SET bal = bal + ? WHERE id=?", (amt, tid))
            db().commit()
            if amt > 0:
                txt = f"> 💰 *На ваш баланс было начислено:* `{amt:.0f}$`\n> *Текущий баланс:* `{fmt((tgt['bal']+amt) - (tgt['pending_withdraw'] or 0))}$`"
            else:
                txt = f"> 💸 *С вашего баланса было списано:* `{abs(amt):.0f}$`\n> *Текущий баланс:* `{fmt((tgt['bal']+amt) - (tgt['pending_withdraw'] or 0))}$`"
            bot.send_message(uid, f"✅ Пользователю {tid} {('начислено' if amt > 0 else 'списано')} {abs(amt)}$")
            try: bot.send_message(tid, txt, parse_mode="MarkdownV2")
            except: pass
            set_st(uid, None); return
        if st == "adm_wait_broadcast":
            txt = m.text.strip()
            cur = db().cursor()
            cur.execute("SELECT id FROM users")
            users = cur.fetchall()
            sent = 0
            for uu in users:
                try:
                    bot.send_message(uu['id'], txt, parse_mode="MarkdownV2")
                    sent += 1
                except:
                    try:
                        bot.send_message(uu['id'], txt)
                        sent += 1
                    except: pass
                time.sleep(0.05)
            bot.send_message(uid, f"✅ Рассылка завершена. Отправлено {sent} пользователям.")
            set_st(uid, None); return
        if st == "adm_wait_block":
            try:
                tid = int(m.text.strip())
            except: bot.send_message(uid, "❌ Неверный ID"); return
            cur = db().cursor()
            cur.execute("UPDATE users SET blocked=1 WHERE id=?", (tid,))
            db().commit()
            bot.send_message(uid, f"✅ Пользователь {tid} заблокирован")
            try: bot.send_message(tid, "> ❌ *Вы заблокированы за нарушение правил бота\\.*", parse_mode="MarkdownV2")
            except: pass
            set_st(uid, None); return
        if st == "adm_wait_unblock":
            try:
                tid = int(m.text.strip())
            except: bot.send_message(uid, "❌ Неверный ID"); return
            cur = db().cursor()
            cur.execute("UPDATE users SET blocked=0 WHERE id=?", (tid,))
            db().commit()
            bot.send_message(uid, f"✅ Пользователь {tid} разблокирован")
            try: bot.send_message(tid, "> ✅ *Вы разблокированы\\.*", parse_mode="MarkdownV2")
            except: pass
            set_st(uid, None); return

    if not u: return

    if st == "wait_phone_queue":
        ph = m.text.strip()
        ok, clean = check_phone(ph)
        if not ok: bot.send_message(uid, "> ❌ *Неверный формат номера\\!*\n> Попробуйте ещё раз\\.", parse_mode="MarkdownV2"); return
        phone = clean
        cur = db().cursor()
        cr = datetime.now().isoformat()
        cur.execute("INSERT INTO orders (drop_id, phone, status, created) VALUES (?, ?, 'in_queue', ?)", (uid, phone, cr))
        db().commit()
        oid = cur.lastrowid
        update_queue_positions()
        pos = get_queue_position(uid)
        cur.execute("UPDATE users SET in_queue=1 WHERE id=?", (uid,))
        db().commit()
        
        txt = f"> ✅ *Номер `{phone}` принят\\!*\n> \n> ⏳ *Ожидайте запроса кода\\.*\n> \n> — _Код должен состоять из 6 цифр\\. Ввод неверных данных карается баном\\._\n> \n> _Если номер не примут в течение 3 минут, появится кнопка продления\\._"
        msg = bot.send_message(uid, txt, parse_mode="MarkdownV2")
        cur.execute("UPDATE users SET queue_msg_id=?, state=NULL, temp=NULL WHERE id=?", (msg.message_id, uid))
        db().commit()
        threading.Thread(target=activity_checker, args=(oid, uid, msg.message_id), daemon=True).start()
        return

    if st == "wait_sum":
        try:
            s = float(m.text.replace(',', '.'))
            if s <= 0: raise
        except: bot.send_message(uid, "❌ Введи число больше 0"); return
        if s < min_withdraw:
            bot.send_message(uid, f"> ❌ *Минимальная сумма вывода:* `{int(min_withdraw)}$`\n> Доступно: `{fmt(get_available_balance(uid))}$`", parse_mode="MarkdownV2")
            return
        avail = get_available_balance(uid)
        if s > avail: bot.send_message(uid, f"> ❌ *Недостаточно средств\\!*\n> Доступный баланс: `{fmt(avail)}$`", parse_mode="MarkdownV2"); set_st(uid, None); return
        
        cur = db().cursor()
        cur.execute("UPDATE users SET pending_withdraw = pending_withdraw + ? WHERE id=?", (s, uid))
        cur.execute("INSERT INTO vyvod (user_id, summa, status, created) VALUES (?, ?, 'wait', ?)", (uid, s, datetime.now().isoformat()))
        db().commit()
        rid = cur.lastrowid
        
        uinf = f"@{u['username']}" if u['username'] else f"id{uid}"
        msg = bot.send_message(admin, f"> 💰 *Заявка на вывод \\#{rid}*\n> \n> *Ник:* {uinf}\n> *Юз/айди:* `{uid}`\n> *Вывод:* `{fmt(s)}$`\n> \n> _Ответьте на это сообщение ссылкой на чек_", parse_mode="MarkdownV2")
        cur.execute("UPDATE vyvod SET admin_msg_id=? WHERE id=?", (msg.message_id, rid))
        db().commit()
        
        bot.send_message(uid, f"> ✅ Заявка на вывод `{fmt(s)}$` создана\\. Ожидайте чек\\.", parse_mode="MarkdownV2")
        set_st(uid, None); return

@bot.callback_query_handler(func=lambda c: c.data.startswith("c_"))
def cold_acts(c):
    d = c.data.split("_")
    act, oid = d[1], int(d[2])
    o = get_o(oid)
    if not o: bot.answer_callback_query(c.id, "❌ Заявка не найдена", show_alert=True); return
    if o['cold_id'] != c.from_user.id: bot.answer_callback_query(c.id, "❌ Только создатель заявки может управлять", show_alert=True); return
    
    if act == "kod":
        request_code_from_drop(oid, o['drop_id'], o['phone'])
        if o['grp_msg_id']:
            try:
                bot.edit_message_text(
                    f"<b>📱 Заявка #{oid}</b>\n\n<b>Номер:</b> <code>{o['phone']}</code>\n\n<b>⏳ Ожидаем код от дропа...</b>",
                    c.message.chat.id, o['grp_msg_id'], parse_mode="HTML"
                )
            except:
                pass
        bot.answer_callback_query(c.id, "✅ Запрос кода отправлен дропу", show_alert=True)
    
    elif act == "pwd":
        request_pwd_from_drop(oid, o['drop_id'], o['phone'])
        if o['grp_msg_id']:
            try:
                bot.edit_message_text(
                    f"<b>📱 Заявка #{oid}</b>\n\n<b>Номер:</b> <code>{o['phone']}</code>\n\n<b>🔐 Ожидаем пароль от дропа...</b>",
                    c.message.chat.id, o['grp_msg_id'], parse_mode="HTML"
                )
            except:
                pass
        bot.answer_callback_query(c.id, "✅ Запрос пароля отправлен дропу", show_alert=True)
    
    elif act == "ok":
        upd_o(oid, status='done', hold_until=(datetime.now()+timedelta(seconds=hold)).isoformat())
        pr = get_price()
        bot.send_message(o['drop_id'], f"> ✅ Номер встал\\. Через 5 минут на ваш баланс будет начислено `{int(pr)}$`", parse_mode="MarkdownV2")
        try:
            bot.send_message(c.message.chat.id, f"✅ Заявка #{oid} — номер встал.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        except:
            pass
        bot.answer_callback_query(c.id, "✅ Готово", show_alert=True)
        
    elif act == "no":
        upd_o(oid, status='cancel')
        bot.send_message(o['drop_id'], "> ❌ Номер слетел\\. Попробуйте сдать другой номер\\.", parse_mode="MarkdownV2")
        try:
            bot.send_message(c.message.chat.id, f"❌ Заявка #{oid} — номер слетел.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        except:
            pass
        bot.answer_callback_query(c.id, "✅ Готово", show_alert=True)
        
    elif act == "skip":
        upd_o(oid, status='cancel')
        txt = (
            f"> ❌ *Номер отклонен\\!*\n"
            f"> Номер `{o['phone']}` помечен как невалидный\\.\n"
            f"> *Возможная причина:* номер заблокирован, слишком много попыток, неверный код\\."
        )
        bot.send_message(o['drop_id'], txt, parse_mode="MarkdownV2")
        try:
            bot.send_message(c.message.chat.id, f"⏭ Заявка #{oid} пропущена.", message_thread_id=o['msg_thread_id'] if o['msg_thread_id'] else None)
        except:
            pass
        bot.answer_callback_query(c.id, "✅ Готово", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == "vyvod_n")
def vyvod(c):
    uid = c.from_user.id
    u = get_u(uid)
    if not u: return
    if u['blocked'] == 1: bot.answer_callback_query(c.id, "❌ Вы заблокированы", show_alert=True); return
    
    avail = get_available_balance(uid)
    if avail < min_withdraw:
        bot.answer_callback_query(c.id, f"‼️ Минимальная сумма вывода: {int(min_withdraw)}$", show_alert=True)
        return
    
    txt = f"> 💸 *Вывод средств*\n> \n> Доступно: `{fmt(avail)}$`\n> Минимальная сумма: `{int(min_withdraw)}$`\n> \n> ✍️ *Введите сумму для вывода*"
    try: bot.edit_message_caption(txt, uid, c.message.message_id, parse_mode="MarkdownV2", reply_markup=back_kb())
    except: bot.send_message(uid, txt, parse_mode="MarkdownV2", reply_markup=back_kb())
    set_st(uid, "wait_sum")
    bot.answer_callback_query(c.id)

if __name__ == "__main__":
    bot.infinity_polling()