import asyncio
import logging
import websockets
import names
import aiofiles
import aiohttp
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK
import datetime


logging.basicConfig(level = logging.INFO)

async def request(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    r = await response.json()
                    return r
                logging.error(f"Error status {response.status} for {url}")
        except aiohttp.ClientConnectionError as e:
            logging.error(f'Connection error {url}: {e}')
        return None

class Server:
    clients = set()

    async def register(self, ws: WebSocketServerProtocol):
        ws.name = names.get_full_name()
        self.clients.add(ws)
        logging.info(f'{ws.remote_address} connects')

    async def unregister(self, ws: WebSocketServerProtocol):
        self.clients.remove(ws)
        logging.info(f'{ws.remote_address} disconnects')


    async def send_to_clients(self, message: str):
        if self.clients:
            [await client.send(message) for client in self.clients]

    async def send_to_client(self, message: str, ws: WebSocketServerProtocol):
           await ws.send(message)

    async def ws_handler(self, ws: WebSocketServerProtocol):
        await self.register(ws)
        try:
            await self.distribute(ws)
        except ConnectionClosedOK:
            pass
        finally:
            await self.unregister(ws)

    async def distribute(self, ws: WebSocketServerProtocol):
        await self.register(ws)

        try:
            async for message in ws:
                if message.startswith('exchange'):
                    await self.handle_exchange_command(message, ws)
                elif message.startswith('buy_convert'):
                    await self.handle_by_convert_command(message, ws)
                elif message.startswith('sell_convert'):
                    await self.handle_sell_convert_command(message, ws)
                else:
                    await self.send_to_clients(f'{ws.name}: {message}')

        except ConnectionClosedOK:
            pass

        finally:
            await self.unregister(ws)

    async def handle_exchange_command(self, message, ws):
        command_parts = message.split(' ')

        if len(command_parts) == 1 and command_parts[0] == 'exchange':
            r = await self.get_exchange()
            await self.send_to_client(r, ws)
            await self.log_exchange_to_file(r)

        elif len(command_parts) == 2 and command_parts[0] == 'exchange':
            days = command_parts[1]
            exchange_history = await self.get_exchange_history(days)
            await self.send_to_client(exchange_history, ws)

        else:
            await self.send_to_client("Invalid command format", ws)

    async def handle_by_convert_command(self, message, ws):
        _, amount_str, selected_currency = message.split(' ')

        try:
            amount = float(amount_str)
            conversion_result = await self.buy_convert(amount, selected_currency)
            await self.send_to_client(conversion_result, ws)
        except ValueError:
            await self.send_to_client('Invalid amount format', ws)

    async def handle_sell_convert_command(self, message, ws):
        _, amount_str, selected_currency = message.split(' ')

        try:
            amount = float(amount_str)
            conversion_result = await self.sell_convert(amount, selected_currency)
            await self.send_to_client(conversion_result, ws)
        except ValueError:
            await self.send_to_client('Invalid amount format', ws)

    async def log_exchange_to_file(self, exchange_info):
        async with aiofiles.open('exchange_log.txt', mode='a') as file:
            await file.write(exchange_info + '\n')

    async def get_exchange_history(self, days):
        if not days.isdigit():
            return "Invalid number of days"

        days = int(days)
        if days <= 0 or days > 10:
            return "Number of days must be between 1 and 10"

        usd_history = await self.get_currency_history("USD", days)
        eur_history = await self.get_currency_history("EUR", days)

        usd_history_str = "\n".join(usd_history)
        eur_history_str = "\n".join(eur_history)

        return f"USD Exchange History:\n{usd_history_str}\n\nEUR Exchange History:\n{eur_history_str}"

    async def get_currency_history(self, currency, days):
        tasks = []
        async with aiohttp.ClientSession() as session:
            for i in range(days, 0, -1):
                date = (datetime.date.today() - datetime.timedelta(days=i)).strftime("%d.%m.%Y")
                url = f"https://api.privatbank.ua/p24api/exchange_rates?json&date={date}"
                tasks.append(self.fetch_data(session, url, currency, date))
            return await asyncio.gather(*tasks)

    async def fetch_data(self, session, url, currency, date):
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    rate = self.extract_currency_rate(data, currency)
                    if rate:
                        return f"{date}:\n{currency}: buy: {rate['purchase']:.5f}, sale: {rate['sale']:.5f}\n"
                    else:
                        return f"{date}: No {currency} rate available"
                else:
                    return f"{date}: No data available"
        except aiohttp.ClientConnectionError as e:
            return f"{date}: Connection error - {e}"

    def extract_currency_rate(self, data, currency):
        exchange_rates = data.get("exchangeRate")
        if exchange_rates:
            for rate in exchange_rates:
                if rate.get("currency") == currency:
                    return {"purchase": rate.get("purchaseRate"), "sale": rate.get("saleRate")}
        return None

    async def get_exchange(self):
        res = await request('https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5')
        usd_exchange = next((el for el in res if el['ccy'] == 'USD'), None)
        eur_exchange = next((el for el in res if el['ccy'] == 'EUR'), None)
        usd_info = f"USD: buy: {usd_exchange['buy']}, sale: {usd_exchange['sale']}" if usd_exchange\
            else "Error: USD exchange rate not found"
        eur_info = f"EUR: buy: {eur_exchange['buy']}, sale: {eur_exchange['sale']}" if eur_exchange \
            else "Error: EUR exchange rate not found"
        return f"{usd_info}\n{eur_info}"

    async def convert(self, amount, selectedCurrency, buying=True):
        res = await request('https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5')
        exchange_rate = None

        for exchange in res:
            if buying and exchange['ccy'] == selectedCurrency and exchange['base_ccy'] == 'UAH':
                exchange_rate = float(exchange['buy'])
            elif not buying and exchange['ccy'] == selectedCurrency and exchange['base_ccy'] == 'UAH':
                exchange_rate = float(exchange['sale'])

        if exchange_rate is not None:
            if buying:
                converted_amount = amount * exchange_rate
                from_currency = selectedCurrency
                to_currency = 'UAH'
            else:
                converted_amount = amount * exchange_rate
                from_currency = selectedCurrency
                to_currency = 'UAH'

            return f'{amount} {from_currency} = {converted_amount:.2f} {to_currency}'
        else:
            return f'Error: {selectedCurrency} exchange rate ({"buying" if buying else "selling"} rate) not found'

    async def buy_convert(self, amount, selectedCurrency):
        return await self.convert(amount, selectedCurrency, buying=True)

    async def sell_convert(self, amount, selectedCurrency):
        return await self.convert(amount, selectedCurrency, buying=False)

async def main():
    server = Server()
    async with websockets.serve(server.ws_handler, 'localhost', 8070):
        await asyncio.Future()

if __name__ == '__main__':
    asyncio.run(main())

