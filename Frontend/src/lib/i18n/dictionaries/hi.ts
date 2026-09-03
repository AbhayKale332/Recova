import type { Dictionary } from "@/lib/i18n/dictionaries/en";

export const hi: Dictionary = {
  locale: { en: "English", hi: "हिन्दी", switchLabel: "भाषा" },

  brand: {
    name: "Recova",
    tagline: "राजस्व वसूली, जो रुकना भी जानती है।",
  },

  nav: {
    console: "कंसोल",
    guardrails: "गार्डरेल्स",
    audit: "ऑडिट",
    landing: "अवलोकन",
    skipToContent: "मुख्य सामग्री पर जाएँ",
    primary: "मुख्य",
  },

  actions: {
    refresh: "रिफ़्रेश",
    refreshing: "रिफ़्रेश हो रहा है…",
    reseed: "डेमो फिर से बनाएँ",
    reseeding: "बनाया जा रहा है…",
    seed: "डेमो बैच बनाएँ",
    seeding: "बनाया जा रहा है…",
    retry: "फिर कोशिश करें",
    close: "बंद करें",
    cancel: "रद्द करें",
    clearFilters: "फ़िल्टर हटाएँ",
    runBatch: "बैच चलाएँ",
    running: "चल रहा है…",
    confirm: "पुष्टि करें",
    export: "CSV निर्यात",
    copy: "कॉपी",
    copied: "कॉपी हो गया",
  },

  states: {
    loadingTitle: "लोड हो रहा है",
    loadingBody: "रिकवरी इंजन से डेटा लाया जा रहा है।",
    emptyTitle: "यहाँ अभी कुछ नहीं है",
    emptyBody: "कोई रिकॉर्ड मेल नहीं खाता।",
    errorTitle: "यह लोड नहीं हो सका",
    unseededTitle: "डेटाबेस खाली है",
    unseededBody:
      "Recova के पास काम करने के लिए अभी कोई केस नहीं है। ट्रांज़ैक्शन, ऑडिट ट्रेल और मेट्रिक्स भरने के लिए डेमो बैच बनाएँ।",
    offlineTitle: "बैकएंड उपलब्ध नहीं",
    offlineBody:
      "API बेस URL पर कोई जवाब नहीं मिला। FastAPI सर्वर चालू करें, फिर दोबारा कोशिश करें।",
  },

  console: {
    title: "रिकवरी कंसोल",
    batchEvidence: "बैच का प्रमाण",
    heroLabel: "वसूल किया गया",
    ofAtRisk: "{amount} जोखिम में से",
    grrr: "सकल राजस्व वसूली दर",
    grrrShort: "GRRR",
    avgTtr: "वसूली में औसत समय",
    avgTtrShort: "औसत TTR",
    inFlight: "प्रक्रिया में",
    inFlightHint: "अभी काम चल रहा है",
    lost: "खोया हुआ",
    lostHint: "सभी रीट्राई ख़त्म",
    atRisk: "जोखिम में",
    funnelTitle: "जोखिम में मौजूद {count} केसों का क्या हुआ",
    funnelHint: "केस सूची फ़िल्टर करने के लिए कोई हिस्सा चुनें।",
    funnelSelected: "{label} पर फ़िल्टर लगा है। हटाने के लिए दोबारा चुनें।",
    caseList: "केस",
    caseCount: "{total} में से {shown} केस",
    lastUpdated: "{when} अपडेट हुआ",
  },

  summary: {
    sentence:
      "Recova ने {cases} केसों में {atRisk} जोखिम में से {recovered} वसूल किए — {escalated} किसी व्यक्ति को सौंपे गए, {stopped} नीति द्वारा रोके गए।",
    sentenceNoCases:
      "Recova के पास अभी जोखिम में कोई केस नहीं है। रिकवरी देखने के लिए डेमो बैच बनाएँ।",
    caseWord: "केस",
    caseWordPlural: "केस",
  },

  funnel: {
    at_risk: "जोखिम में",
    intervened: "हस्तक्षेप किया",
    recovered: "वसूल किया",
    escalated: "व्यक्ति के पास",
    cancelled: "नीति द्वारा रोका गया",
    failed: "खोया हुआ",
  },

  status: {
    PENDING: "लंबित",
    DIAGNOSING: "निदान हो रहा है",
    WAITING: "प्रतीक्षा में",
    INTERVENING: "हस्तक्षेप जारी",
    RECOVERED: "वसूल किया गया",
    ESCALATED: "व्यक्ति के पास",
    CANCELLED: "रोका गया",
    FAILED: "खोया हुआ",
  },

  statusMeaning: {
    PENDING: "पहचाना गया, अभी काम शुरू नहीं",
    DIAGNOSING: "मूल कारण पता किया जा रहा है",
    WAITING: "जानबूझकर रोका गया",
    INTERVENING: "संपर्क जारी है",
    RECOVERED: "पैसा प्राप्त हुआ",
    ESCALATED: "नियमानुसार व्यक्ति को सौंपा गया",
    CANCELLED: "एक स्टॉपिंग रूल ने रोका — गार्डरेल्स ने काम किया",
    FAILED: "सभी रीट्राई ख़त्म हो गए",
  },

  filters: {
    label: "फ़िल्टर",
    search: "खोजें",
    searchPlaceholder: "ग्राहक या ट्रांज़ैक्शन आईडी",
    failureClass: "समस्या",
    status: "स्थिति",
    archetype: "पंक्ति का प्रकार",
    all: "सभी",
    archetypeCase: "रिकवरी केस",
    archetypeHealthy: "स्वस्थ (केवल संदर्भ)",
    archetypeNonRecoverable: "वसूली योग्य नहीं",
    active: "{count} फ़िल्टर सक्रिय",
    activePlural: "{count} फ़िल्टर सक्रिय",
  },

  table: {
    customer: "ग्राहक",
    amount: "राशि",
    problem: "समस्या",
    status: "स्थिति",
    playbook: "प्लेबुक",
    confidence: "विश्वास",
    ttr: "TTR",
    caseId: "केस",
    noPlaybook: "अभी तय नहीं",
    notRecovered: "—",
  },

  batch: {
    confirmTitle: "{count} केसों पर रिकवरी चलाएँ?",
    confirmBody:
      "Recova {amount} मूल्य के {count} केसों पर काम करेगा। हर केस असली रिकवरी लूप से गुज़रेगा — निदान, संपर्क, स्टॉपिंग रूल।",
    skipped: "फ़िल्टर किए गए {count} केस पहले ही बंद हैं और छोड़ दिए जाएँगे।",
    noneRunnable: "फ़िल्टर किए गए किसी भी केस पर काम नहीं हो सकता — सभी पहले ही बंद हैं।",
    capped: "बैकएंड एक बार में 50 केस लेता है; पहले 50 चलाए जाएँगे।",
    localeNote: "संपर्क संदेश {language} में लिखे जाएँगे।",
    successTitle: "बैच पूरा हुआ",
    successBody: "{total} में से {recovered} वसूल किए गए।",
    failureTitle: "बैच विफल रहा",
  },

  toast: { dismiss: "हटाएँ", notifications: "सूचनाएँ" },

  errors: {
    withStatus: "{method} {path} ने {status} लौटाया।",
    network: "{base} पर बैकएंड से संपर्क नहीं हो सका।",
    aborted: "अनुरोध रद्द किया गया।",
    unknown: "कुछ विफल हुआ और बैकएंड ने कोई कारण नहीं बताया।",
    seedFailed: "डेमो बैच नहीं बन सका।",
    seedOk: "{count} ट्रांज़ैक्शन बनाए गए।",
  },

  landing: { comingSoon: "अवलोकन" },
  guardrails: { title: "गार्डरेल्स" },
  audit: { title: "ऑडिट ट्रेल" },
};
