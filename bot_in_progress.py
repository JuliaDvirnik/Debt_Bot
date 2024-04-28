# check commit
# импортируем библиотеки для работы с ботом
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardRemove, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, \
    InlineKeyboardButton

from pydrive2.auth import GoogleAuth
from oauth2client.service_account import ServiceAccountCredentials
from pydrive2.drive import GoogleDrive

from config import TOKEN

import pickle
import math

# для бэкапов
gauth = GoogleAuth()
scope = ['https://www.googleapis.com/auth/drive']
gauth.credentials = ServiceAccountCredentials.from_json_keyfile_name(
    'bot-transaction-service-account-key.json', scope)
drive = GoogleDrive(gauth)


# создание класса для хранения наших операций
class Transaction:
    def __init__(self, debitor_id, debitor_name, date=None, creditor_id=None, creditor_name=None, amount=None,
                 comment=None):
        self.debitor_id = debitor_id
        self.debitor_name = debitor_name
        self.creditor_name = creditor_name
        self.creditor_id = creditor_id
        self.amount = amount
        self.comment = comment
        self.date = date


class user_states:  # Enumeration
    start = 0
    i_dept = 1
    i_debt_to_person = 2
    i_debt_to_person_money = 4  # + ожидается комментарий
    i_create_new_debt = 10  # + ожидается подтверждение, верно всё или нет
    i_request_debt = 11
    i_request_debt_to_person = 12
    i_request_debt_to_person_money = 13
    i_create_new_query = 14  # + ожидается подтверждение, верно всё иил нет
    show_summary = 5
    show_detalization = 7
    show_detalization_with_person = 8

    default_states = [0, 1, 5, 7, 11]




class Session:
    def __init__(self, debt: Transaction = None):
        self.transaction_in_progress: Transaction = debt
        self.state = user_states.start


class debtBot:
    def __init__(self, TOKEN):

        self.bot = Bot(token=TOKEN)
        self.dp = Dispatcher(self.bot)

        # хранение транзакции в процессе её создания и состояние пользователя
        self.user_session = {}

        # хранение всех транзакций
        self.transaction_list = []

        # хранение пользователей
        self.administrator_id = 990039224
        self.users = {}
        self.google_folder_id = "10bBx8zxO1kqvmrEvKPQhq-fHdJjYPvx_"  # todo здесь резервная папка! надо, чтобы для каждого бота была своя

        self.register_events()

        try:
            with open('transactions.pkl', 'rb') as f:
                self.transaction_list = pickle.load(f)
                print("Transaction list loaded")
        except FileNotFoundError:
            print("Transaction list did not loaded")
        try:
            with open('users.pkl', 'rb') as f:
                self.users = pickle.load(f)
                print("Dict of users loaded")
        except FileNotFoundError:
            print("Dict of users did not loaded")
        print(self.users)

    def start_polling(self):
        print('go')
        executor.start_polling(self.dp)
        print('polling stopped')

    def register_events(self):
        # вместо декораторов
        self.dp.register_message_handler(self.process_start_command, commands=['start'])
        self.dp.register_message_handler(self.process_help_command, commands=['help'])
        self.dp.register_message_handler(self.process_callback_amount)
        self.dp.register_callback_query_handler(self.process_begining, lambda c: c.data == 'give_menu')
        self.dp.register_callback_query_handler(self.process_callback_debt, lambda c: c.data == 'debt')
        self.dp.register_callback_query_handler(self.process_callback_person_debt,
                                                lambda c: c.data.startswith('debt_of_'))
        self.dp.register_callback_query_handler(self.process_callback_user_checking_debt,
                                                lambda c: c.data == 'user_checking_debt')
        self.dp.register_callback_query_handler(self.process_callback_registration_debt,
                                                lambda c: c.data == 'registration_debt')
        self.dp.register_callback_query_handler(self.process_callback_reset_user_state,
                                                lambda c: c.data == 'reset_user_state')
        self.dp.register_callback_query_handler(self.process_callback_query_debt, lambda c: c.data == 'query_debt')
        self.dp.register_callback_query_handler(self.process_callback_person_query_debt,
                                                lambda c: c.data.startswith('query_debt_of_'))
        self.dp.register_callback_query_handler(self.process_callback_user_checking_query_debt,
                                                lambda c: c.data == 'user_checking_query_debt')
        self.dp.register_callback_query_handler(self.process_callback_send_query_debt,
                                                lambda c: c.data == 'send_query_debt')
        self.dp.register_callback_query_handler(self.process_callback_registration_query_debt,
                                                lambda c: c.data.startswith('query_'))
        self.dp.register_callback_query_handler(self.process_callback_reset_query_debt,
                                                lambda c: c.data.startswith('no_query_debt_'))
        self.dp.register_callback_query_handler(self.process_callback_detalisation, lambda c: c.data == 'detalisation')
        self.dp.register_callback_query_handler(self.process_callback_person_detalisation,
                                                lambda c: c.data.startswith('detalisation_of_'))
        self.dp.register_callback_query_handler(self.process_callback_numb_detalisation,
                                                lambda c: c.data.startswith('detail_'))
        self.dp.register_callback_query_handler(self.process_callback_summary, lambda c: c.data == 'summary')
        self.dp.register_callback_query_handler(self.process_callback_allperson_summary,
                                                lambda c: c.data.startswith('summary_all'))
        self.dp.register_callback_query_handler(self.process_callback_person_summary,
                                                lambda c: c.data.startswith('summary_of_'))

    # КОМАНДА СТАРТ
    async def process_start_command(self, message: types.Message):
        user_id = message.chat.id
        user_name = message.chat.first_name
        if user_id not in self.users:
            self.users[user_id] = user_name
            print("Новый пользователь ", user_name)
            with open('users.pkl', 'wb') as f:
                pickle.dump(self.users, f)
                print("Dict of users was written")
        await self.if_user_has_session(message)
        await self.process_begining_mes(message)

    # НАЖАТА КНОПКА "give menu"
    async def process_begining(self, callback_query: types.CallbackQuery):
        message = callback_query.message
        await self.process_begining_mes(message)

    async def process_begining_mes(self, message: types.Message):
        debt_btn = InlineKeyboardButton('Я должен!', callback_data='debt')
        query_debt_btn = InlineKeyboardButton('Запросить долг', callback_data='query_debt')
        summary_btn = InlineKeyboardButton('Показать подытог', callback_data='summary')
        detalization_btn = InlineKeyboardButton('Детализация операций', callback_data='detalisation')
        inline_kb = InlineKeyboardMarkup(row_width=2).add(debt_btn, query_debt_btn).add(summary_btn).add(
            detalization_btn)
        await message.answer("Пора пораскинуть деньжатами! \nВыбери, что бы ты хотел сделать?", reply_markup=inline_kb)

    # КОМАНДА HELP
    async def process_help_command(self, message: types.Message):
        await self.if_user_has_session(message)
        await message.answer("Чтобы начать работу, нажми на кнопку: \n\n[ Я должен! ] - создаст новый долг "
                             "\n\n[ Показать подытог ] - покажет, сколько денег ты должен определенному человеку "
                             "\n\n[ Детализация операций ] - восстановит историю операций, если есть сомнения"
                             "\n\nДля начала работы нужно нажать на кнопку.\n\nСвязь с разработчиком @teplo_toy")

    # НАЖАТА КНОПКА debt
    async def process_callback_debt(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            buttons = []
            for id, name in self.users.items():
                if id == user_id:
                    continue
                else:
                    inline_btn = InlineKeyboardButton(name, callback_data='debt_of_' + str(id))
                    buttons.append(inline_btn)
            inline_kb = InlineKeyboardMarkup(row_width=2).add(*buttons)
            await callback_query.message.answer("Выберете человека, которому должны денег", reply_markup=inline_kb)
            self.user_session[user_id].state = user_states.i_dept
            print("State ", self.user_session[user_id].state, " for " + user_name)
            await callback_query.answer()
        else:
            await self.calling_reset_user_state(callback_query)

    async def calling_reset_user_state(self, callback_query):
        user_id = callback_query.message.chat.id
        non_reset_state = user_states.default_states
        if self.user_session[user_id].state not in non_reset_state:
            inline_btn = InlineKeyboardButton("Обнулиться", callback_data="reset_user_state")
            inline_kb = InlineKeyboardMarkup().add(inline_btn)
            await callback_query.message.answer("Если не хотите продолжать, что начали, нажмите на кнопку",
                                                reply_markup=inline_kb)

    # НАЖАТА КНОПКА debt_of_
    async def process_callback_person_debt(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            message = callback_query.message
            user_id = message.chat.id
            user_name = callback_query.message.chat.first_name
            debt = Transaction(user_id, user_name)
            self.user_session[user_id].transaction_in_progress = debt
            print("New transaction in process for ", user_name)
            creditor_id = int(callback_query.data[8:])  # 8 here is len('dept_of_')
            transaction = self.user_session[user_id].transaction_in_progress
            transaction.creditor_id = creditor_id
            transaction.creditor_name = self.users[creditor_id]
            await message.answer("Хорошо. Теперь введите сумму, которую вы должны, в EUR. "
                                 "\nИспользуйте только цифры.\nЕсли число не целое, используйте точку или запятую")
            self.user_session[user_id].state = user_states.i_debt_to_person
            print("State ", self.user_session[user_id].state, " for " + user_name)
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА user_checking_debt
    async def process_callback_user_checking_debt(self, callback_query: types.CallbackQuery):
        message = callback_query.message
        necessary_state = [user_states.i_debt_to_person_money]
        if await self.checking_user_state(necessary_state, callback_query.message):
            await self.process_callback_user_checking_debt_message(message)
        else:
            await self.calling_reset_user_state(callback_query)

    async def process_callback_user_checking_debt_message(self, message: types.Message):
        user_id = message.chat.id
        user_name = message.chat.first_name
        transaction = self.user_session[user_id].transaction_in_progress
        transaction.date = message.date
        text_debt = "Должник: " + transaction.debitor_name + "\nКредитор: " + \
                    transaction.creditor_name + "\nСумма: €" + f'{transaction.amount:.2f}'
        if transaction.comment is not None:
            text_debt += "\nКомментарий: " + transaction.comment
        right_debt_btn = InlineKeyboardButton('Да, внести долг в базу', callback_data='registration_debt')
        wrong_debt_btn = InlineKeyboardButton('Давай по новой, Миша, всё хуйня', callback_data='reset_user_state')
        inline_kb = InlineKeyboardMarkup(row_width=1).add(right_debt_btn, wrong_debt_btn)
        await message.answer("Долг, который вы собираетесь внести:\n\n" + text_debt + "\n\nВсё верно?",
                             reply_markup=inline_kb)
        self.user_session[user_id].state = user_states.i_create_new_debt
        print("State ", self.user_session[user_id].state, " for " + user_name)

    # НАЖАТА КНОПКА registration_debt
    async def process_callback_registration_debt(self, callback_query: types.CallbackQuery):
        necessary_state = [user_states.i_create_new_debt]
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            transaction = self.user_session[user_id].transaction_in_progress
            another_user_id = transaction.creditor_id
            another_user_name = transaction.creditor_name
            amount = transaction.amount
            comment = transaction.comment
            self.transaction_list.append(transaction)
            with open('transactions.pkl', 'wb') as f:
                pickle.dump(self.transaction_list, f)
                print("Transaction list was written")
            summary_message = await self.summary(user_id, another_user_id)
            continue_btn = InlineKeyboardButton('Го ещё что-нибудь сделаем', callback_data='give_menu')
            inline_kb = InlineKeyboardMarkup().add(continue_btn)
            await callback_query.message.answer("Ваш долг записан!\n\n" + summary_message + another_user_name,
                                                reply_markup=inline_kb)
            print("New debt is written by " + user_name)
            self.user_session[user_id].state = user_states.start
            print("State ", self.user_session[user_id].state, " for " + user_name)
            self.user_session[user_id].transaction_in_progress = None

            # сохраняем бекап на гугл диск

            await self.save_backups()

            # пишем пользователю о новом долге
            message = "Поздравляю!\n" + user_name + " должен вам €" + str(amount) + "."
            if comment is not None:
                message += "\nКоммент: " + comment
            await self.bot.send_message(another_user_id, message)

        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА reset_user_state
    async def process_callback_reset_user_state(self, callback_query: types.CallbackQuery):
        await self.if_user_has_session(callback_query.message)
        user_id = callback_query.message.chat.id
        user_name = callback_query.message.chat.first_name
        self.user_session[user_id].state = user_states.start
        print("State ", self.user_session[user_id].state, " for " + user_name)
        if self.user_session[user_id].transaction_in_progress is not None:
            self.user_session[user_id].transaction_in_progress = None
        await self.process_begining_mes(callback_query.message)

    # НАЖАТА КНОПКА query_debt
    async def process_callback_query_debt(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            buttons = []
            for id, name in self.users.items():
                if id == user_id:
                    continue
                else:
                    inline_btn = InlineKeyboardButton(name, callback_data='query_debt_of_' + str(id))
                    buttons.append(inline_btn)
            inline_kb = InlineKeyboardMarkup(row_width=2).add(*buttons)
            await callback_query.message.answer("Выберете человека, который вам должен", reply_markup=inline_kb)
            self.user_session[user_id].state = user_states.i_request_debt
            print("State ", self.user_session[user_id].state, " for " + user_name)
            await callback_query.answer()
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА query_debt_of_
    async def process_callback_person_query_debt(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            message = callback_query.message
            user_id = message.chat.id
            user_name = callback_query.message.chat.first_name
            debitor_id = int(callback_query.data[14:len(callback_query.data)]) # 14 is len() of query_debt_of_
            debt = Transaction(debitor_id, self.users[debitor_id])
            self.user_session[user_id].transaction_in_progress = debt
            print("New query transaction in process for ", user_name)
            transaction = self.user_session[user_id].transaction_in_progress
            transaction.creditor_id = user_id
            transaction.creditor_name = user_name
            await message.answer("Хорошо. Теперь введите сумму, которую вам должны, в EUR. "
                                 "\nИспользуйте только цифры.\nЕсли число не целое, используйте точку или запятую")
            self.user_session[user_id].state = user_states.i_request_debt_to_person
            print("State ", self.user_session[user_id].state, " for " + user_name)
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА user_checking_query_debt
    async def process_callback_user_checking_query_debt(self, callback_query: types.CallbackQuery):
        necessary_state = [user_states.i_request_debt_to_person_money]
        message = callback_query.message
        if await self.checking_user_state(necessary_state, message):
            await self.process_callback_user_checking_query_debt_mes(message)
        else:
            await self.calling_reset_user_state(callback_query)

    async def process_callback_user_checking_query_debt_mes(self, message: types.Message):
        user_id = message.chat.id
        user_name = message.chat.first_name
        transaction = self.user_session[user_id].transaction_in_progress
        transaction.date = message.date
        text_debt = "Должник: " + transaction.debitor_name + "\nКредитор: " + \
                    transaction.creditor_name + "\nСумма: €" + f'{transaction.amount:.2f}'
        if transaction.comment is not None:
            text_debt += "\nКомментарий: " + transaction.comment
        right_debt_btn = InlineKeyboardButton('Да, отправить запрос на долг', callback_data='send_query_debt')
        wrong_debt_btn = InlineKeyboardButton('Давай по новой, Миша, всё хуйня', callback_data='reset_user_state')
        inline_kb = InlineKeyboardMarkup(row_width=1).add(right_debt_btn, wrong_debt_btn)
        await message.answer("Долг, который вы хотите запросить:\n\n" + text_debt + "\n\nВсё верно?",
                             reply_markup=inline_kb)
        self.user_session[user_id].state = user_states.i_create_new_query
        print("State ", self.user_session[user_id].state, " for " + user_name)

    # НАЖАТА КНОПКА send_query_debt
    async def process_callback_send_query_debt(self, callback_query: types.CallbackQuery):
        necessary_state = [user_states.i_create_new_query]
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            transaction = self.user_session[user_id].transaction_in_progress
            another_user_id = transaction.debitor_id
            another_user_name = transaction.debitor_name
            amount = f'{transaction.amount:.2f}'
            comment = transaction.comment
            continue_btn = InlineKeyboardButton('Го ещё что-нибудь сделаем', callback_data='give_menu')
            inline_kb = InlineKeyboardMarkup().add(continue_btn)
            await callback_query.message.answer(
                "Ваш запрос отправлен должнику на проверку!\nЕсли он его подтвердит, долг будет внесен в базу.",
                reply_markup=inline_kb)
            print("New debt query is send by " + user_name + " to " + another_user_name)

            # пишем пользователю запрос
            message = "Ого! Кто-то думает, что вы ему должны!\n\nВам пришел запрос на такой долг:\nДолжник: " + another_user_name + "\nКредитор: " + user_name + "\nСумма: €" + amount

            if comment is not None:
                message += "\nКоммент: " + comment

            message += "\n\nВы согласны принять на себя эту ответственность?"
            query_yes_btn = InlineKeyboardButton('Да, внести долг в базу', callback_data='query_' + str(user_id))
            query_no_btn = InlineKeyboardButton('Нет, у меня лапки', callback_data='no_query_debt_' + str(user_id))
            inline_kb = InlineKeyboardMarkup(row_width=1).add(query_yes_btn, query_no_btn)
            await self.bot.send_message(another_user_id, message, reply_markup=inline_kb)

            self.user_session[user_id].state = user_states.start
            print("State ", self.user_session[user_id].state, " for " + user_name)
            self.user_session[user_id].transaction_in_progress = None
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА query_
    async def process_callback_registration_query_debt(self, callback_query: types.CallbackQuery):
        await self.if_user_has_session(callback_query.message)
        debitor_id = callback_query.message.chat.id
        debitor_name = callback_query.message.chat.first_name
        message_id = callback_query.message.message_id
        creditor_id = int(callback_query.data[6:len(callback_query.data)])   # 6 is len of query_
        creditor_name = self.users[creditor_id]
        date = callback_query.message.date
        text_message = callback_query.message.text
        text_lines = text_message.split("\n")
        amount = float(text_lines[5][8:])   # 5 is order number of string with amount, 8 is len() of "Сумма: €"
        if len(text_lines) == 8:   # 8 is amount of strings in case no comment
            comment = None
        else:
            comment = text_lines[6][9:]   # 6 is order number of string with comment, 9 is len() of "Коммент: "
        transaction = Transaction(debitor_id, debitor_name, date, creditor_id, creditor_name, amount, comment)
        self.transaction_list.append(transaction)
        with open('transactions.pkl', 'wb') as f:
            pickle.dump(self.transaction_list, f)
            print("Transaction list was written")
        summary_message = await self.summary(debitor_id, creditor_id)
        continue_btn = InlineKeyboardButton('Го ещё что-нибудь сделаем', callback_data='give_menu')
        inline_kb = InlineKeyboardMarkup().add(continue_btn)
        await callback_query.message.answer("Ваш долг записан!\n\n" + summary_message + creditor_name,
                                            reply_markup=inline_kb)
        print("New debt is written by " + str(debitor_name))

        # изменяем сообщение с подтверждением долга
        new_text = 'Здесь был запрос на долг от ' + creditor_name + " на сумму €" + str(
            amount) + ", который вы одобрили"
        await self.bot.edit_message_text(chat_id=debitor_id, message_id=message_id, text=new_text)
        # todo вопрос - удаляются ли кнопки, и редачится ли сообщение, если прошло больше 48 часов

        # сохраняем бекап на гугл диск
        await self.save_backups()

        # пишем пользователю о новом долге
        message = "Неплохо!\n" + debitor_name + " одобрил запрошенный долг на сумму €" + str(amount) + "."
        await self.bot.send_message(creditor_id, message)

    # Функция, которая сохраняет бекап на гугл диск
    async def save_backups(self):
        folder_id = self.google_folder_id
        query = "'{}' in parents and trashed=false".format(folder_id)
        file_list = drive.ListFile({'q': query}).GetList()
        if len(file_list) == 0:
            gfile = drive.CreateFile({'parents': [{'id': folder_id}]})
            gfile.SetContentFile('transactions.pkl')
            gfile.Upload()  # сохраняем новый файл
            print("New transaction backup is created")
        else:
            last_file_id = file_list[0]['id']
            gfile = drive.CreateFile({'id': last_file_id})
            gfile.SetContentFile('transactions.pkl')
            gfile.Upload()  # обновляем уже существующий файл
            print("Transaction backup is updated")

    # НАЖАТА КНОПКА no_query_debt_
    async def process_callback_reset_query_debt(self, callback_query: types.CallbackQuery):
        await self.if_user_has_session(callback_query.message)
        debitor_id = callback_query.message.chat.id
        debitor_name = callback_query.message.chat.first_name
        message_id = callback_query.message.message_id
        creditor_id = int(callback_query.data[14:len(callback_query.data)]) # 14 is len of no_query_debt_
        creditor_name = self.users[creditor_id]
        text_message = callback_query.message.text
        text_lines = text_message.split("\n")
        amount = text_lines[5][8:]   # 5 is order number of string with amount, 8 is len() of "Сумма: €"

        # пишем пользователю об отклонении нового долга
        message = "WARNING!\n" + debitor_name + " отклонил запрошенный долг на сумму €" + str(
            amount) + "." + "\nПохоже," \
                            " вам есть, что обсудить"
        await self.bot.send_message(creditor_id, message)

        # изменяем сообщение с подтверждением долга
        new_text = 'Вы отклонили запрос на долг от ' + creditor_name + " на сумму €" + amount + ".\nПохоже, вам надо " \
                                                                                                "поговорить.\nЕсли что, кнопка о принятии долга всё ещё работает!"
        await callback_query.message.answer(new_text)
        query_yes_btn = InlineKeyboardButton('Передумал, должен!', callback_data='query_' + str(creditor_id))
        inline_kb = InlineKeyboardMarkup().add(query_yes_btn)
        await self.bot.edit_message_text(chat_id=debitor_id, message_id=message_id, text=text_message,
                                    reply_markup=inline_kb)
        # todo вопрос - удаляются ли кнопки, и редачится ли сообщение, если прошло больше 48 часов

    # НАЖАТА КНОПКА detalisation
    async def process_callback_detalisation(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            buttons = []
            for id, name in self.users.items():
                if id == user_id:
                    continue
                else:
                    inline_btn = InlineKeyboardButton(name, callback_data='detalisation_of_' + str(id))
                    buttons.append(inline_btn)
            inline_kb = InlineKeyboardMarkup().add(*buttons)
            await callback_query.message.answer("Выберете человека, c которым хотите посмотреть детализацию операций",
                                                reply_markup=inline_kb)
            self.user_session[user_id].state = user_states.show_detalization
            print("State ", self.user_session[user_id].state, " for " + user_name)
            await callback_query.answer()
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА detalisation_of_
    async def process_callback_person_detalisation(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            another_user_id = callback_query.data[16:len(callback_query.data)]   # 16 is len() of detalisation_of_
            detail_10_btn = InlineKeyboardButton('10 последних', callback_data='detail_10_' + another_user_id)
            detail_30_btn = InlineKeyboardButton('30 последних', callback_data='detail_30_' + another_user_id)
            detail_all_btn = InlineKeyboardButton('Все!', callback_data='detail_00_' + another_user_id)
            inline_kb = InlineKeyboardMarkup(row_width=1).add(detail_10_btn, detail_30_btn, detail_all_btn)
            await callback_query.message.answer("Сколько операций вы хотите посмотреть?", reply_markup=inline_kb)
            self.user_session[user_id].state = user_states.show_detalization_with_person
            print("State ", self.user_session[user_id].state, " for " + user_name)
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА detail_
    async def process_callback_numb_detalisation(self, callback_query: types.CallbackQuery):
        necessary_state = [user_states.show_detalization_with_person]
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            another_user_id = int(callback_query.data[10:])   # 10 is len() of detail_XX_
            another_user_name = self.users[another_user_id]
            numb_of_detail = int(callback_query.data[7:9])   # 7 and 9 - indices of numb of depth detaisation (10, 30 or 00)
            if numb_of_detail == 0:
                numb_of_detail = float("inf")
            text_message = ""
            numb_check = 0
            for i in range(len(self.transaction_list) - 1, -1, -1):
                if numb_check < numb_of_detail:
                    transaction = self.transaction_list[i]
                    if transaction.debitor_id == user_id and transaction.creditor_id == another_user_id:
                        amount = "-" + f'{transaction.amount:.2f}'
                        text_message_1 = "{}\n€ {}".format(str(transaction.date)[0:11], amount)   # 11 is len of date (we dont take time)
                        if transaction.comment is None:
                            text_message_1 += "\n\n"
                        else:
                            text_message_1 += "\nКоммент: " + transaction.comment + "\n\n"
                        text_message = text_message_1 + text_message
                        numb_check += 1

                    elif transaction.creditor_id == user_id and transaction.debitor_id == another_user_id:
                        amount = "+" + f'{transaction.amount:.2f}'
                        text_message_1 = "{}\n€ {}".format(str(transaction.date)[0:11], amount)   # 11 is len of date (we dont take time)
                        if transaction.comment is None:
                            text_message_1 += "\n\n"
                        else:
                            text_message_1 += "\nКоммент: " + transaction.comment + "\n\n"
                        text_message = text_message_1 + text_message
                        numb_check += 1

                else:
                    break
            if numb_check == 0:
                text_message_add = "Я не могу сделать детализацию, т.к. с этим человеком не найдено ни одной финансовой операции!"
            else:
                text_message_add = "Ваша детализация c " + another_user_name + " готова!\n\n"
            continue_btn = InlineKeyboardButton('Го ещё что-нибудь сделаем', callback_data='give_menu')
            inline_kb = InlineKeyboardMarkup().add(continue_btn)
            await callback_query.message.answer(text_message_add + text_message, reply_markup=inline_kb)
            print("New detalization is ready for " + user_name)
            self.user_session[user_id].state = user_states.start
            print("State ", self.user_session[user_id].state, " for " + user_name)
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА summary
    async def process_callback_summary(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            buttons = []
            additional_button = InlineKeyboardButton("ВСЕОБЩАЯ ДЕТАЛИЗАЦИЯ", callback_data='summary_all')
            for id, name in self.users.items():
                if id == user_id:
                    continue
                else:
                    inline_btn = InlineKeyboardButton(name, callback_data='summary_of_' + str(id))
                    buttons.append(inline_btn)
            inline_kb = InlineKeyboardMarkup().add(*buttons).add(additional_button)
            await callback_query.message.answer("Выберете человека, c которым хотите посмотреть подытог",
                                                reply_markup=inline_kb)
            self.user_session[user_id].state = user_states.show_summary
            print("State ", self.user_session[user_id].state, " for " + user_name)
            await callback_query.answer()
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА summary_all
    async def process_callback_allperson_summary(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            all_text_message = "Вот подытог по всем пользователям бота:\n"

            for user in self.users:
                if user != user_id:
                    another_user_id = user
                    another_user_name = self.users[another_user_id]
                    text_message = await self.summary(user_id, another_user_id)
                    all_text_message += "\n" + text_message + another_user_name

            continue_btn = InlineKeyboardButton('Го ещё что-нибудь сделаем', callback_data='give_menu')
            inline_kb = InlineKeyboardMarkup().add(continue_btn)
            await callback_query.message.answer(all_text_message, reply_markup=inline_kb)
            print("New summary is ready for " + user_name)
            self.user_session[user_id].state = user_states.start
            print("State ", self.user_session[user_id].state, " for " + user_name)
        else:
            await self.calling_reset_user_state(callback_query)

    # НАЖАТА КНОПКА summary_of_
    async def process_callback_person_summary(self, callback_query: types.CallbackQuery):
        necessary_state = user_states.default_states
        if await self.checking_user_state(necessary_state, callback_query.message):
            user_id = callback_query.message.chat.id
            user_name = callback_query.message.chat.first_name
            another_user_id = int(callback_query.data[11:len(callback_query.data)])   # 11 is len of summary_of_
            another_user_name = self.users[another_user_id]

            text_message = await self.summary(user_id, another_user_id)
            continue_btn = InlineKeyboardButton('Го ещё что-нибудь сделаем', callback_data='give_menu')
            inline_kb = InlineKeyboardMarkup().add(continue_btn)
            await callback_query.message.answer(text_message + another_user_name, reply_markup=inline_kb)
            print("New summary is ready for " + user_name)
            self.user_session[user_id].state = user_states.start
            print("State ", self.user_session[user_id].state, " for " + user_name)
        else:
            await self.calling_reset_user_state(callback_query)

    async def summary(self, user_id, another_user_id):
        summary = 0
        for transaction in self.transaction_list:
            if transaction.debitor_id == user_id and transaction.creditor_id == another_user_id:
                summary -= transaction.amount
            elif transaction.creditor_id == user_id and transaction.debitor_id == another_user_id:
                summary += transaction.amount
            else:
                continue
        if summary > 0:
            text_message = f"Вам должен €{summary:.2f} этот человек: "
        elif summary < 0:
            text_message = f"Вы должны €{-summary:.2f} этому человеку: "
        else:
            text_message = "У вас нулевые долги с этим человеком: "
        return text_message

    # ОТСЛЕЖИВАЕМ СООБЩЕНИЯ В ЧАТЕ
    async def process_callback_amount(self, message: types.Message):
        user_id = message.chat.id
        user_name = message.chat.first_name
        await self.if_user_has_session(message)
        if user_id == self.administrator_id and message.text.startswith("@all "):
            message_for_all = message.text[5:]   # 5 is len of "@all "
            for user in self.users:
                await self.bot.send_message(user, message_for_all)

        if self.user_session[user_id].state == user_states.i_debt_to_person:
            transaction = self.user_session[user_id].transaction_in_progress
            message_amount = message.text.replace(",", ".")
            try:
                amount = float(message_amount)
                if amount < 0:
                    await message.answer("Нельзя вписать отрицательный долг, хитрец! \nВведите положительное число.")
                elif amount == 0:
                    await message.answer("Нельзя вписать 0, иначе зачем мы здесь! Введите свой долг!")
                elif not math.isfinite(amount):
                    await message.answer("Не балуйся! Надо ввести нормальное число")
                elif amount <= 0.01:
                    await message.answer("Вы ввели слишком маленькое число! Я вам не верю!")
                elif amount >= 15000:
                    await message.answer("Вы ввели слишком большое число! Я вам не верю!")
                else:
                    print("Была введена сумма: ", amount)
                    transaction.amount = amount
                    no_comment_btn = InlineKeyboardButton('Не хочу оставлять!', callback_data='user_checking_debt')
                    inline_kb1 = InlineKeyboardMarkup().add(no_comment_btn)
                    await message.answer("Оставьте комментарий к данному долгу", reply_markup=inline_kb1)
                    self.user_session[user_id].state = user_states.i_debt_to_person_money
                    print("State ", self.user_session[user_id].state, " for " + user_name)

            except ValueError:
                await message.answer("То, что вы ввели, не похоже на сумму. Попробуйте ещё раз. \
                \nИспользуйте только цифры. Можете использовать точку или запятую. \nНапример, вы можете ввести 4 или 4.0 или 4.25")

        elif self.user_session[user_id].state == user_states.i_request_debt_to_person:
            transaction = self.user_session[user_id].transaction_in_progress
            message_amount = message.text.replace(",", ".")
            try:
                amount = float(message_amount)
                if amount < 0:
                    await message.answer("Нельзя вписать отрицательный долг \nВведите положительное число.")
                elif amount == 0:
                    await message.answer("Нельзя вписать 0, иначе зачем мы здесь! Введите свой долг!")
                elif not math.isfinite(amount):
                    await message.answer("Не балуйся! Надо ввести нормальное число")
                elif amount <= 0.01:
                    await message.answer("Вы ввели слишком маленькое число! Я вам не верю!")
                elif amount >= 15000:
                    await message.answer("Вы ввели слишком большое число! Я вам не верю!")
                else:
                    print("Была введена сумма: ", amount)
                    transaction.amount = amount
                    no_comment_btn = InlineKeyboardButton('Не хочу оставлять!',
                                                          callback_data='user_checking_query_debt')
                    inline_kb1 = InlineKeyboardMarkup().add(no_comment_btn)
                    await message.answer("Оставьте комментарий к данному долгу", reply_markup=inline_kb1)
                    self.user_session[user_id].state = user_states.i_request_debt_to_person_money
                    print("State ", self.user_session[user_id].state, " for " + user_name)

            except ValueError:
                await message.answer("То, что вы ввели, не похоже на сумму. Попробуйте ещё раз. \
                    \nИспользуйте только цифры. Можете использовать точку или запятую. \nНапример, вы можете ввести 4 или 4.0 или 4.25")

        elif self.user_session[user_id].state == user_states.i_debt_to_person_money:
            transaction = self.user_session[user_id].transaction_in_progress
            comment = message.text
            transaction.comment = comment
            transaction.date = message.date
            print("Был введен комментарий: ", comment)
            await self.process_callback_user_checking_debt_message(message)

        elif self.user_session[user_id].state == user_states.i_request_debt_to_person_money:
            transaction = self.user_session[user_id].transaction_in_progress
            comment = message.text
            transaction.comment = comment
            transaction.date = message.date
            print("Был введен комментарий: ", comment)
            await self.process_callback_user_checking_query_debt_mes(message)

        else:
            await message.answer("Не пишите мне лишних сообщений! Нажимайте на кнопки")

    # ФУНКЦИИ
    # функция, которая проверяет, соотвествует ли state пользователя для кнопки, которую от нажал, если нет - подсказывает
    async def checking_user_state(self, necessary_state: list, message: types.Message):
        await self.if_user_has_session(message)
        user_id = message.chat.id
        user_state = self.user_session[user_id].state
        if user_state in necessary_state:
            return True
        else:
            cases = {0: 'Для начала работы нажмите на кнопку "Я должен", "Показать подытог" или "Детализация операций"',
                     1: 'Ваш долг в процессе создания! Выберите человека, которому вы должны.\nИспользуйте кнопки.',
                     2: 'Ваш долг в процессе создания! Введите сумму, которую вы должны.\nОтправьте мне её сообщением',
                     4: 'Ваш долг в процессе создания! Введите комментарий к долгу.\nОтправьте мне его сообщением',
                     5: 'Ваш подытог уже формируется! Выберите человека, с которым вы хотите его посмотреть.\nИспользуйте кнопки.',
                     7: 'Ваша детализация уже формируется! Выберите человека, с которым вы хотите ее посмотреть.\nИспользуйте кнопки.',
                     8: 'Ваша детализация уже формируется! Выберите количество операций.\nИспользуйте кнопки.',
                     10: 'Ваш долг создан, но ещё не занесен в базу!\nИспользуйте кнопки, чтобы записать долг или стереть его, если что-то пошло не так.',
                     11: 'Ваш запрос на долг в процессе создания!\nВыберите человека, которой вам должен. Используйте кнопки.',
                     12: 'Ваш запрос на долг в процессе создания! Введите сумму, которую вам должны.\nОтправьте мне её сообщением',
                     13: 'Ваш запрос на долг в процессе создания! Введите комментарий к операции.\nОтправьте мне его сообщением',
                     14: 'Ваш запрос на долг создан, но ещё не отправлен должнику!\nИспользуйте кнопки, чтобы отправить запрос или стереть его, если что-то пошло не так.'}
            await message.answer(cases[user_state])
            return False

    async def if_user_has_session(self, message: types.Message):
        user_id = message.chat.id
        user_name = message.chat.first_name
        if user_id not in self.user_session:
            new_session = Session()
            self.user_session[user_id] = new_session
            print("New session for " + user_name + " is created")
            print("State ", new_session.state, " for " + user_name)


def main():
    print('starting...')
    debt_bot = debtBot(TOKEN)
    debt_bot.start_polling()


if __name__ == '__main__':
    main()
