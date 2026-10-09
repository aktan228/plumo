export type Channel = "WhatsApp" | "Telegram" | "Instagram";
export type Mode = "ai" | "waiting" | "human";
export type Message = { id: string; role: "customer" | "ai" | "human" | "event"; text: string; time: string };
export type Conversation = {
  id: string; name: string; initials: string; channel: Channel; mode: Mode;
  unread: number; contact: string; language: string; summary: string; need: string;
  next: string; messages: Message[];
};

export function exampleConversations(en: boolean): Conversation[] {
  return [
    {
      id: "aibek-wa", name: en ? "Aibek T." : "Айбек Т.", initials: "АТ", channel: "WhatsApp", mode: "waiting", unread: 2,
      contact: "Айбек · WhatsApp", language: en ? "Russian" : "Русский",
      summary: en ? "Looking for a two-bedroom apartment in central Bishkek. Budget up to $80,000. Would like a viewing on Saturday." : "Ищет двухкомнатную квартиру в центре Бишкека. Бюджет до $80 000. Хочет посмотреть варианты в субботу.",
      need: en ? "Two-bedroom apartment · centre · up to $80,000" : "2 комнаты · центр · до $80 000",
      next: en ? "Manager to check options and confirm viewing time." : "Менеджеру нужно подобрать варианты и согласовать время просмотра.",
      messages: [
        { id: "a1", role: "customer", text: en ? "Hi! Looking for a two-bedroom apartment, up to $80,000." : "Здравствуйте! Ищу двушку до 80 тысяч долларов.", time: "10:24" },
        { id: "a2", role: "ai", text: en ? "Hi! Which area would you prefer?" : "Здравствуйте! В каком районе вы рассматриваете квартиру?", time: "10:24" },
        { id: "a3", role: "customer", text: en ? "In the centre. Can I view it on Saturday?" : "В центре. Можно посмотреть в субботу?", time: "10:25" },
        { id: "a4", role: "ai", text: en ? "I'll pass your request to a manager to check options and agree a time. The viewing is not confirmed yet." : "Передам пожелания менеджеру: он проверит варианты и согласует время. Просмотр пока не подтверждён.", time: "10:25" },
        { id: "a5", role: "event", text: en ? "Waiting for a manager · automatic replies paused" : "Ожидает менеджера · автоматические ответы приостановлены", time: "10:25" },
        { id: "a6", role: "customer", text: en ? "Great, preferably after lunch." : "Хорошо, желательно после обеда.", time: "10:26" },
      ],
    },
    {
      id: "alina-tg", name: en ? "Alina K." : "Алина К.", initials: "АК", channel: "Telegram", mode: "ai", unread: 1,
      contact: "@alina_example", language: en ? "Russian" : "Русский",
      summary: en ? "Asking about renting an apartment. The agent is clarifying location and budget." : "Интересуется арендой квартиры. Агент уточняет район и бюджет.",
      need: en ? "Apartment rental" : "Аренда квартиры", next: en ? "Clarify location and budget." : "Уточнить район и бюджет.",
      messages: [
        { id: "b1", role: "customer", text: en ? "Hi, do you help with apartment rentals?" : "Добрый день, вы помогаете с арендой квартиры?", time: "09:48" },
        { id: "b2", role: "ai", text: en ? "Hi! Tell me which area and monthly budget you have in mind." : "Добрый день! Подскажите, какой район и бюджет в месяц вы рассматриваете?", time: "09:48" },
      ],
    },
    {
      id: "timur-ig", name: en ? "Timur S." : "Тимур С.", initials: "ТС", channel: "Instagram", mode: "human", unread: 0,
      contact: "@timur_example", language: en ? "Russian" : "Русский",
      summary: en ? "Interested in a commercial property. A manager is checking the details." : "Интересуется коммерческим помещением. Менеджер уточняет детали.",
      need: en ? "Commercial property · around 60 m²" : "Коммерческое помещение · около 60 м²",
      next: en ? "Check approved property information." : "Проверить данные помещения в утверждённых материалах.",
      messages: [
        { id: "c1", role: "customer", text: en ? "Interested in a commercial space, around 60 square metres." : "Интересует помещение под магазин, около 60 квадратов.", time: "09:12" },
        { id: "c2", role: "event", text: en ? "Manager took the conversation · automatic replies paused" : "Менеджер взял диалог · автоматические ответы приостановлены", time: "09:15" },
        { id: "c3", role: "human", text: en ? "Hi! I'm checking the details. Which area would suit you?" : "Здравствуйте! Уточняю детали. Какой район вам подойдёт?", time: "09:16" },
      ],
    },
    {
      id: "nurai-wa", name: en ? "Nurai A." : "Нурай А.", initials: "НА", channel: "WhatsApp", mode: "ai", unread: 0,
      contact: "Нурай · WhatsApp", language: en ? "Russian" : "Русский",
      summary: en ? "Asking about buying an apartment. Waiting for budget details." : "Спрашивает о покупке квартиры. Ожидаем уточнение бюджета.",
      need: en ? "Apartment purchase" : "Покупка квартиры", next: en ? "Clarify budget and number of rooms." : "Уточнить бюджет и количество комнат.",
      messages: [
        { id: "d1", role: "customer", text: en ? "I want to buy an apartment. Where should I start?" : "Хочу купить квартиру. С чего начать?", time: "Вчера" },
        { id: "d2", role: "ai", text: en ? "Tell me your budget and how many rooms you need, so we can understand your request." : "Расскажите о бюджете и нужном количестве комнат, чтобы мы поняли вашу задачу.", time: "Вчера" },
      ],
    },
  ];
}

export type DialogueAction =
  | { type: "read"; id: string }
  | { type: "mode"; id: string; mode: "ai" | "human"; event: Message }
  | { type: "send"; id: string; message: Message };

export function updateConversations(conversations: Conversation[], action: DialogueAction): Conversation[] {
  return conversations.map(conversation => {
    if (conversation.id !== action.id) return conversation;
    if (action.type === "read") return { ...conversation, unread: 0 };
    if (action.type === "mode") {
      if (conversation.mode === action.mode) return conversation;
      return { ...conversation, mode: action.mode, unread: 0, messages: [...conversation.messages, action.event] };
    }
    // Check ownership again when applying a send, not just when displaying the composer.
    if (conversation.mode !== "human" || action.message.role !== "human" || !action.message.text.trim() || action.message.text.length > 2000 || conversation.messages.some(message => message.id === action.message.id)) return conversation;
    return { ...conversation, messages: [...conversation.messages, { ...action.message, text: action.message.text.trim() }] };
  });
}
