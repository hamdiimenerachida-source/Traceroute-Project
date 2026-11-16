md = """# Traceroute – Visualisation des chemins réseau

Ce projet permet d'observer le chemin emprunté par les paquets réseau depuis une connexion en Algérie vers plusieurs serveurs situés dans différentes régions du monde, puis de représenter les sauts sur une carte.

## Fonctionnalités

- Mesure des temps de réponse avec des sondes ICMP et, lorsque l'hôte ne répond pas à l'ICMP, avec une connexion TCP sur le port 443.
- Identification des routeurs traversés à chaque valeur de TTL.
- Géolocalisation approximative des sauts et affichage des routes sur une carte.
- Comparaison des résultats avec la commande `tracert` de Windows.
- Analyse des échanges ICMP avec Wireshark.

## Outils utilisés

- **Python** : réalisation du traceroute et génération des cartes.
- **Sockets brutes et ICMP** : envoi des sondes et réception des réponses.
- **Wireshark** : observation et vérification des paquets.
- **tracert (Windows)** : comparaison du chemin obtenu.

## Organisation des scripts

- `traceroute.py` : exécution du traceroute, avec trois sondes par TTL et une limite de 30 TTL.
- `step1_hosts.py` : étape de sélection et de test des hôtes.
- `trace_map.py` : génération des cartes représentant les chemins.

## Méthode

Les destinations sont choisies dans plusieurs régions : Algérie, Europe, Asie, Australie et Amérique du Sud. Un contrôle basé sur le temps aller-retour minimal théorique permet d'écarter certaines destinations dont la latence serait incompatible avec la ville annoncée. Ce contrôle indique seulement si une localisation est plausible ; il ne confirme pas l'emplacement réel du serveur.

Pour chaque destination, le programme relève les sauts visibles, les temps de réponse et les éventuelles absences de réponse. Les résultats sont ensuite représentés sur une carte et comparés, pour `www.us.es`, à ceux de `tracert`.

## Observations principales

- Les serveurs algériens testés restent dans le réseau national jusqu'à leur destination.
- Plusieurs routes internationales passent par le réseau Level 3 (AS3356).
- Les routes vers l'Asie et l'Australie présentent une augmentation importante du temps de réponse après la sortie d'Algérie.
- Certains routeurs ne répondent pas aux sondes ICMP ; le chemin peut donc rester partiellement observable.
- Les positions affichées sur la carte sont approximatives. Les noms DNS inverses peuvent parfois donner une indication plus fiable sur la ville d'un routeur.

## Limites

La géolocalisation par adresse IP ne fournit pas une position exacte. De plus, certains routeurs filtrent les messages ICMP ou utilisent des adresses privées qui ne peuvent pas être localisées sur la carte. Les temps de réponse peuvent également varier entre deux exécutions.
