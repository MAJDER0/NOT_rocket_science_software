# Overview

xD

## Do oryginalnego repozytorium zostały dodane:

* Warstwa stacji naziemnej, która automatyzuje cały lot rakiety w symulatorze. Zawiera klienta do komunikacji z rakietą, logikę sekwencji startu i prostego autopilota: tankowanie, grzanie, uzbrojenie, zapłon, wykrywanie apogeum, wyrzucenie spadochronu i lądowanie

* Prototypowa implementacja protokołu komunikacyjnego w Ruście, gdzie enkoduje ramki w sposob analogiczny do tego w pythonie

## Foldery i pliki dodane:

**1. ground_station:**
   - flight_controller.py
   - launch_sequencer.py
   - rocket_client.py

**2. rust_protocol:**
   - crc.rs
   - frame.rs
   - lib.rs
   - tests/encode_demo.rs

## Prezentacja

### Symulacja Lotu Rakiety: ###

https://github.com/user-attachments/assets/9e47ab9a-4539-4bf6-a52c-134257a17958

### Test jednostkowy Enkodowania ramki protokołu komunikacyjnego w Rust: ###

https://github.com/user-attachments/assets/d09c9729-24d3-400a-ace6-5eed1b037f6f

## Jak odpalić? 

1. Symulacja lotu rakiety (z root directory):
   
      - Terminal #1
       
             python tcp_proxy.py
       
      - Terminal #2
        
              python tcp_simulator.py --verbose
      
      - Terminal #3
        
              python ground_station/launch_sequencer.py
  
2. Test Encodera ramek protokołu komunikacyjnego w Rust (root/rust_protocol):
   
   - Terminal #1

           cargo test -- --nocapture


# Dokumentacja

## flight_controller.py

**Prosty automat stanów lotu z podstawowymi zabezpieczeniami**


*Metody kluczowe:*

   - **tank_oxidizer() / tank_fuel()** : otwiera zawory, czeka aż poziom = 100%, zamyka
   - **heat_oxidizer()** : włącza grzałkę utleniacza, czeka aż ciśnienie będzie w oknie zapłonu (55–65 bar), pilnuje żeby nie eksplodowało
   - **ignition_sequence()** : odpala silnik z kontrolą bezpieczeństwa (intake’y zamknięte, dobre ciśnienie, sekwencja zawory → zapalnik)
   - **climb_and_detect_apogee()** : śledzi wysokość, wykrywa apogeum
   - **descent_and_chute()** : w fazie spadania decyduje kiedy wyrzucić spadochron (nie za wysoko, nie za szybko, albo awaryjnie po ok. 9s), potem czeka aż rakieta „przestanie spadać” i uznaje lądowanie
   - **full_auto_mission()** – klei to wszystko w jedną misję od tankowania do lądowania i przerywa jeśli coś pójdzie w ABORT

## rocket_client.py

**klient wysokiego poziomu, który łączy się z rakietą przez TCP, wysyła komendy (zawory, zapłon, spadochron) i zbiera telemetrię w tle**

*Metody kluczowe:*

   - **set_servo_position(name, pos)** : rusza serwem / zaworem (np. „otwórz fuel_main”)
   - **relay_open(name) / relay_close(name)** : włącza/wyłącza przekaźniki (grzałka, igniter, spadochron)
   - **get_telem(key) / get_all_telem()** : daje ostatnie znane wartości sensorów (poziom paliwa, ciśnienie, wysokość, itd)

## launch_sequencer.py

**skrypt, który odpala pełną misję automatycznie, krok po kroku**

      1. Ładuje config simulator_config.yaml
   
      2. Tworzy RocketClient i FlightController
   
      3. Czeka chwilę na pierwszą telemetrię
   
      4. Odpala full_auto_mission()
   
      5. Na końcu wyświetla stan misji i ostatnią telemetrię

## crc.rs

**implementacja CRC32 MPEG-2 dokładnie w tym formacie, którego używa protokół**

    * Liczy CRC32 MPEG-2 dokładnie tak, jak robi to kod po stronie Pythona

    * Robi padding do 4 bajtów, przerabia dane na słowa 32-bit, liczy CRC32 wg polinomu protokołu i zwraca 4 bajty CRC

## frame.rs

**struktura ramki + funkcje pakujące pola i odwracające bity tak jak w pierwotnym protokole**

*Metody kluczowe:*

   - **FrameFields** : pola nagłówka ramki (destination, device_id, itd) + 4 bajty payloadu

   - **pack_frame_bits()** : buduje surowe 10 bajtów (nagłówek + pola + payload). Docelowo ten sam bit-pack co w Pythonie

   - **reverse_all_bytes() / reverse_bits_in_byte()** : odwracanie kolejności bitów w każdym bajcie

## lib.rs

**główny encoder ramki: pakuje pola, odwraca bity, liczy CRC i składa finalne 14 bajtów do wysłania**

**Sklejka całości**

*Metody kluczowe:*

   - **encode_frame(frame)** :

           1. pakuje pola do 10 bajtów 
         
           2. odwraca bity w każdym bajcie 
         
           3. liczy CRC32 
         
           4. dokleja CRC.

## encode_demo.rs

**Test jednostkowy który pokazuje, że encoder w Ruście działa i daje sensowne wyjście**

      1. Buduje przykładową ramkę „ustaw serwo w pozycję 0”
      
      2. Przepuszcza ją przez encode_frame
      
      3. Wypisuje bajty i sprawdza, że wynik ma 14 bajtów (10 danych + 4 CRC)

