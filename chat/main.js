console.log('Running...');

const ws = new WebSocket('ws://127.0.0.1:8070');

ws.onopen = () => {
    console.log('WebSocket connect');
};

const formChat = document.getElementById('formChat');
const textField = document.getElementById('textField');
const exchangeResult = document.getElementById('exchangeResult');
const amountField = document.getElementById('amountField');
const buyButton = document.getElementById('buyButton');
const sellButton = document.getElementById('sellButton');
const result = document.getElementById('result');

formChat.addEventListener('submit', (e) => {
    e.preventDefault();
    const command = textField.value;
    ws.send(command);
    exchangeResult.textContent = 'Waiting for the result...';
    textField.value = '';
});

buyButton.addEventListener('click', async () => {
    const amount = parseFloat(amountField.value);
    const selectedCurrency = currencySelect.value;
    if (!isNaN(amount)) {
        const response = await handleConversion(amount, selectedCurrency, true);
        exchangeResult.textContent = response;
    } else {
        result.textContent = 'Amount format is incorrect';
    }
    amountField.value = '';
});

sellButton.addEventListener('click', async () => {
    const amount = parseFloat(amountField.value);
    const selectedCurrency = currencySelect.value;
    if (!isNaN(amount)) {
        const response = await handleConversion(amount, selectedCurrency, false);
        exchangeResult.textContent = response;
    } else {
        result.textContent = 'Amount format is incorrect';
    }
    amountField.value = '';
});

ws.onmessage = (e) => {
    console.log(e.data);
    const data = e.data.split('\n');
    data.forEach((line) => {
        if (line) {
            const elMsg = document.createElement('div');
            elMsg.textContent = line;
            elMsg.classList.add('exchange-line');
            exchangeResult.appendChild(elMsg);
        }
    });
};

async function handleConversion(amount, selectedCurrency, buying) {
    const command = `${buying ? 'buy' : 'sell'}_convert ${amount} ${selectedCurrency}`;
    ws.send(command);

    return new Promise((resolve) => {
        const messageHandler = (e) => {
            ws.removeEventListener('message', messageHandler);
            resolve(e.data);
        };
        ws.addEventListener('message', messageHandler);
    });
}
