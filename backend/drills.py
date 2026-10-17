"""
drills.py — Exercícios de pronúncia focados nas dificuldades típicas de brasileiros.

Cada item tem a frase/palavra a ler e o som trabalhado. Pares mínimos (ship × sheep)
treinam a diferença entre dois sons que o português não distingue.
"""

DRILLS: dict[str, list[dict]] = {
    "en": [
        {"sound": "θ", "title": "th surdo (think)", "items": [
            "think", "three", "thank you", "I think it's Thursday.", "Three thin thieves thought a thousand thoughts.",
        ], "pairs": [["think", "sink"], ["three", "tree"], ["thank", "tank"]]},
        {"sound": "ð", "title": "th sonoro (this)", "items": [
            "this", "the", "mother", "This is the other one.", "My brother and father are there.",
        ], "pairs": [["they", "day"], ["then", "den"], ["though", "dough"]]},
        {"sound": "iː", "title": "i longo × i curto (sheep × ship)", "items": [
            "sheep", "ship", "leave", "live", "Please sit in this seat.",
        ], "pairs": [["sheep", "ship"], ["leave", "live"], ["seat", "sit"], ["beach", "bitch"]]},
        {"sound": "æ", "title": "a aberto (cat)", "items": [
            "cat", "bad", "happy", "The black cat sat on the mat.", "That man has a bag.",
        ], "pairs": [["bad", "bed"], ["man", "men"], ["sad", "said"]]},
        {"sound": "h", "title": "h aspirado (house)", "items": [
            "house", "hello", "happy", "He has a huge house.", "How have you been?",
        ], "pairs": [["hat", "at"], ["hair", "air"], ["heat", "eat"]]},
        {"sound": "ɹ", "title": "r inglês (red)", "items": [
            "red", "very", "around", "Rory runs really fast.", "The red car is right there.",
        ], "pairs": [["right", "light"], ["road", "load"], ["very", "berry"]]},
        {"sound": "_final", "title": "consoante final, sem vogal extra (big)", "items": [
            "big", "dog", "book", "I like big black dogs.", "Stop that cab at the club.",
        ], "pairs": []},
        {"sound": "_s", "title": "s + consoante, sem 'i' antes (speak)", "items": [
            "speak", "study", "school", "Students speak Spanish at school.", "Stop and start again.",
        ], "pairs": []},
    ],
    "es": [
        {"sound": "r", "title": "rr vibrante (perro)", "items": [
            "perro", "rojo", "carro", "El perro corre rápido.", "Erre con erre, cigarro.",
        ], "pairs": [["perro", "pero"], ["carro", "caro"], ["cerro", "cero"]]},
        {"sound": "x", "title": "jota (jamón)", "items": [
            "jamón", "gente", "ojo", "Juan juega en el jardín.", "Los jóvenes generales.",
        ], "pairs": [["jamón", "ramón"], ["ajo", "aro"]]},
        {"sound": "s", "title": "s sem virar z (casa)", "items": [
            "casa", "mesa", "rosa", "La casa de Rosa es preciosa.", "Esa mesa es pesada.",
        ], "pairs": []},
        {"sound": "e", "title": "vogais fechadas e/o", "items": [
            "café", "pero", "todo", "Ese perro es todo negro.", "Somos once personas.",
        ], "pairs": []},
        {"sound": "l", "title": "l final (español)", "items": [
            "español", "sol", "papel", "El sol de abril es genial.", "Hablo español con Manuel.",
        ], "pairs": []},
    ],
}


def drills_for(lang: str) -> list[dict]:
    return DRILLS.get(lang, [])
