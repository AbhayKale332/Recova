"""Offline conversation and call scripts used to populate realistic recovery histories."""

from __future__ import annotations

from dataclasses import dataclass ,field

from application .constants import (
CallSpeaker ,
CallStatus ,
MessageDirection ,
MessageSender ,
MessageStatus ,
)

AGENT =MessageSender .AGENT
CUSTOMER =MessageSender .CUSTOMER
SYSTEM =MessageSender .SYSTEM
OUT =MessageDirection .OUTBOUND
IN =MessageDirection .INBOUND


@dataclass
class MsgBeat :
    direction :MessageDirection
    sender :MessageSender
    body :str
    status :MessageStatus =MessageStatus .READ
    meta :dict |None =None


@dataclass
class CallTurnBeat :
    speaker :CallSpeaker
    text :str
    at_offset_sec :int


@dataclass
class CallBeat :
    status :CallStatus
    duration_sec :int
    outcome :str
    turns :list [CallTurnBeat ]


@dataclass
class Thread :
    messages :list [MsgBeat ]=field (default_factory =list )
    call :CallBeat |None =None


    p2p_phrase :str |None =None



PERSONAS =[
{"ok":"Done, thanks!","p2p":"5 tarikh ko kar denge","greet":"ji"},
{"ok":"Paid just now ✅","p2p":"agle hafte tak clear kar dunga","greet":"haan"},
{"ok":"ok completed","p2p":"parso pakka payment ho jayega","greet":"ji bilkul"},
{"ok":"sorted, cheers","p2p":"3 din mein transfer kar denge","greet":"hello"},
{"ok":"done ✔️","p2p":"kal subah kar dunga","greet":"namaste"},
{"ok":"thik hai, ho gaya","p2p":"10 tareekh tak account clear kar denge","greet":"ji"},
]


def persona_for (index :int )->dict :
    return PERSONAS [index %len (PERSONAS )]


def build_call (
*,
failure_class :int ,
name :str ,
amount_inr :float ,
persona :dict ,
)->CallBeat :
    """A short AI-voice-agent call transcript for a transaction (per class).

    Used by the on-demand "Call" action so any transaction can be called, not
    only the seeded ones. The transcript is what the simulated agent would say;
    a live provider (Vapi / ElevenLabs / LiveKit) replaces this later.
    """
    rupees =f"₹{int (amount_inr ):,}"
    greet =persona ["greet"]
    first =name .split ()[0 ]

    scripts ={
    1 :[
    (CallSpeaker .AGENT ,f"Namaste {first } {greet }, support team se bol raha hoon. Aapke {rupees } payment mein ek technical glitch aa gaya tha — humari taraf se. Main abhi ek secure link bhej raha hoon.",0 ),
    (CallSpeaker .CUSTOMER ,"Haan theek hai, bhej do.",5 ),
    (CallSpeaker .AGENT ,"Bhej diya. Ek tap mein ho jayega, OTP ki zaroorat nahi.",11 ),
    (CallSpeaker .CUSTOMER ,"Ok, kar deta hoon.",16 ),
    ],
    2 :[
    (CallSpeaker .AGENT ,f"Hello {first } {greet }, aapka {rupees } ka checkout OTP step pe ruk gaya tha. Main UPI Autopay ka ek 1-tap link bhej raha hoon.",0 ),
    (CallSpeaker .CUSTOMER ,"Achha, wahi problem ho rahi thi.",6 ),
    (CallSpeaker .AGENT ,"Koi baat nahi, is link se seedha ho jayega. Bhej diya WhatsApp pe.",12 ),
    (CallSpeaker .CUSTOMER ,"Perfect, dekh leta hoon.",18 ),
    ],
    3 :[
    (CallSpeaker .AGENT ,f"Namaste {first } {greet }, aapka auto-pay mandate refresh karna tha. Ek chhota ₹2 test authorization bhej rahe hain.",0 ),
    (CallSpeaker .CUSTOMER ,"Haan bhej do.",6 ),
    (CallSpeaker .AGENT ,f"Ho gaya, mandate active hai. Salary date pe {rupees } apne aap cut ho jayega.",12 ),
    (CallSpeaker .CUSTOMER ,"Badhiya, dhanyavaad.",19 ),
    ],
    4 :[
    (CallSpeaker .AGENT ,f"Namaste {first } {greet }, invoice ke {rupees } outstanding ke baare mein call kiya tha. Payment kab tak expect kar sakte hain?",0 ),
    (CallSpeaker .CUSTOMER ,persona ["p2p"],7 ),
    (CallSpeaker .AGENT ,"Bilkul, main note kar leta hoon aur tab tak reminders rok deta hoon. Dhanyavaad!",14 ),
    ],
    }
    turns =[CallTurnBeat (sp ,txt ,off )for sp ,txt ,off in scripts .get (failure_class ,scripts [1 ])]
    return CallBeat (
    status =CallStatus .COMPLETED ,
    duration_sec =(turns [-1 ].at_offset_sec +6 ),
    outcome ="ai_voice_recovery",
    turns =turns ,
    )


def build_thread (
*,
failure_class :int ,
outcome :str ,
name :str ,
amount_inr :float ,
persona :dict ,
payment_link :str ,
invoice_no :str ,
salary_date :str ,
)->Thread :
    rupees =f"₹{int (amount_inr ):,}"

    if failure_class ==1 :
        t =Thread (messages =[
        MsgBeat (OUT ,AGENT ,
        f"Namaste {name }, we hit a brief technical glitch on our side while processing your {rupees } payment — nothing wrong on your end. Here's a secure 1-tap link to finish, no OTP needed: {payment_link }",
        meta ={"payment_link":payment_link }),
        ])
        if outcome =="recovered":
            t .messages +=[
            MsgBeat (IN ,CUSTOMER ,persona ["ok"]),
            MsgBeat (OUT ,SYSTEM ,f"Payment of {rupees } captured on the fallback rail ✓"),
            ]
        elif outcome =="late_settlement":
            t .messages +=[
            MsgBeat (OUT ,SYSTEM ,f"Original {rupees } settled late on the primary rail — fallback voided so you're not charged twice (NO_DOUBLE_CHARGE) ✓"),
            ]
        return t

    if failure_class ==2 :
        t =Thread (messages =[
        MsgBeat (OUT ,AGENT ,
        f"Hi {name }! Looks like your {rupees } checkout didn't go through at the OTP step. Skip the friction — pay in 1 tap via UPI Autopay: {payment_link }",
        meta ={"payment_link":payment_link }),
        ])
        if outcome =="recovered":
            t .messages +=[
            MsgBeat (IN ,CUSTOMER ,persona ["ok"]),
            MsgBeat (OUT ,SYSTEM ,f"Payment of {rupees } captured via UPI Autopay ✓"),
            ]
        elif outcome =="cross_device":
            t .messages +=[
            MsgBeat (OUT ,SYSTEM ,f"Payment of {rupees } completed on another device — further reminders stopped (CROSS_DEVICE_COMPLETION) ✓"),
            ]
        elif outcome =="cancelled_optout":
            t .messages +=[
            MsgBeat (IN ,CUSTOMER ,"please stop messaging me, band karo"),
            MsgBeat (OUT ,SYSTEM ,"Opt-out detected — all further contact stopped (OPT_OUT)."),
            ]
        return t

    if failure_class ==3 :
        t =Thread (messages =[
        MsgBeat (OUT ,AGENT ,
        f"Hi {name }, your auto-debit of {rupees } didn't go through — looks like a low balance before your salary date. No worries, we'll retry around {salary_date }."),
        ])
        if outcome =="recovered":
            t .messages +=[
            MsgBeat (IN ,CUSTOMER ,persona ["ok"]),
            MsgBeat (OUT ,SYSTEM ,f"Retry on {salary_date } succeeded — {rupees } captured ✓"),
            ]

            t .call =CallBeat (
            status =CallStatus .COMPLETED ,duration_sec =38 ,outcome ="mandate_refreshed",
            turns =[
            CallTurnBeat (CallSpeaker .AGENT ,f"Namaste {name } {persona ['greet']}, main support team se bol raha hoon. Aapka auto-pay mandate refresh karna tha, ek chhota sa ₹2 test authorization bhej rahe hain.",0 ),
            CallTurnBeat (CallSpeaker .CUSTOMER ,"Haan theek hai, bhej do.",6 ),
            CallTurnBeat (CallSpeaker .AGENT ,"Ho gaya, mandate active hai. Salary date pe {rupees} apne aap cut ho jayega.".replace ("{rupees}",rupees ),12 ),
            CallTurnBeat (CallSpeaker .CUSTOMER ,"Perfect, dhanyavaad.",20 ),
            ],
            )
        elif outcome =="cancelled_rbi":
            t .messages +=[
            MsgBeat (OUT ,SYSTEM ,"3 auto-debit retries reached — stopped per RBI cap (RBI_MAX_RETRIES)."),
            ]
        return t


    t =Thread (messages =[
    MsgBeat (OUT ,AGENT ,
    f"Namaste {name }, this is a reminder that invoice {invoice_no } for {rupees } is now overdue. When can we expect the payment?"),
    ])
    if outcome =="recovered":
        t .p2p_phrase =persona ["p2p"]
        t .messages +=[MsgBeat (IN ,CUSTOMER ,persona ["p2p"])]


    elif outcome =="escalated_dispute":
        t .messages +=[
        MsgBeat (IN ,CUSTOMER ,"yeh invoice galat hai, humne itna order nahi kiya tha"),
        MsgBeat (OUT ,SYSTEM ,"Dispute raised — automation frozen, escalated to a human (DISPUTE_FREEZE)."),
        ]
    return t
