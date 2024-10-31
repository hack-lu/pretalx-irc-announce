import json
import time
import datetime
import requests
import threading
import random
import sys
from irc.bot import SingleServerIRCBot

import configparser
import readline


class ScheduleAnnouncer(SingleServerIRCBot):
    def get_irc_room(self, room_name):
        normalized_name = room_name.strip().lower()  # Normalize input for lookup
        for key in self.room_mapping:
            if key.strip().lower() == normalized_name:
                return self.room_mapping[key]
        return "Room not found"

    def show_rooms(self):
        print("Available IRC rooms:")
        for idx, (room_name, channel) in enumerate(self.room_mapping.items(), start=1):
            print(f"  {idx}: {room_name} -> {channel}")
        self.room_index_mapping = {str(idx): channel for idx, (_, channel) in enumerate(self.room_mapping.items(), start=1)}

    def __init__(self, config_file, json_file=None):
        config = configparser.ConfigParser()
        config.read(config_file)

        server = config['IRC']['Server']
        port = int(config['IRC']['Port'])
        nickname = config['IRC']['Nickname']
        self.nickserv_password = config['IRC']['NickServPassword']

        api_url = config['API']['ApiUrl']
        api_token = config['API']['ApiToken']

        super().__init__([(server, port)], nickname, nickname)
        self.room_mapping = {room: channel for room, channel in config['ROOM_MAPPING'].items()}
        self.announced_talks = set()
        self.started_talks = set()
        self.ended_talks = set()
        self.json_file = json_file
        self.api_url = api_url
        self.api_token = api_token
        self.running = True  # Flag to control the running state
        self.debug_current_time = None  # Set to None to use real current time
        self.simulating = False
        self.simulation_speed = 1

        self.load_schedule()

        # Start a thread to listen for command line input
        threading.Thread(target=self.command_listener, daemon=True).start()

    def load_schedule(self):
        if self.json_file:
            self.schedule = self.load_schedule_from_file(self.json_file)
        elif self.api_url and self.api_token:
            self.schedule = self.load_schedule_from_api(self.api_url, self.api_token)
        else:
            raise ValueError("Either json_file or api_url and api_token must be provided.")

    def load_schedule_from_file(self, json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
            print("Loaded schedule from JSON file.")  # Debug output
            return data['schedule']['conference']['days']

    def load_schedule_from_api(self, api_url, api_token):
        headers = {'Authorization': f'Token {api_token}'}
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            print("Loaded schedule from API.")  # Debug output
            return data['schedule']['conference']['days']
        else:
            raise ConnectionError(f"Failed to fetch schedule from API: {response.status_code}")

    def command_listener(self):
        self.command_history = []
        def completer(text, state):
            commands = ["reload", "now", "agenda", "today", "time", "speed", "quit", "set_start_time", "notify_room", "help", "rooms"]
            buffer = readline.get_line_buffer().strip()
            if len(buffer.split()) == 1:
                # Root level: provide command suggestions
                options = [cmd for cmd in commands if cmd.startswith(text)]
            else:
                options = []
            if state < len(options):
                return options[state]
            else:
                return None
        readline.set_completer(completer)
        readline.parse_and_bind('tab: complete')

        def set_start_time(args):
            try:
                start_time = datetime.datetime.strptime(args, "%Y-%m-%d %H:%M")
                self.debug_current_time = start_time
                print(f"Start time set to: {self.debug_current_time}")
            except ValueError:
                print("Invalid date format. Use 'YYYY-MM-DD HH:MM'.")
        while self.running:
            command = input("Enter command: ")
            self.command_history.append(command)
            readline.add_history(command)
            self.command_history.append(command)
            readline.add_history(command)
            self.command_history.append(command)
            readline.add_history(command)
            if command.strip().startswith("set_start_time"):
                args = command[len("set_start_time"):].strip()
                set_start_time(args)
            if command.strip().lower() == "reload":
                print("Reloading schedule...")
                self.load_schedule()
            elif command.strip().lower() == "now":
                self.show_current_sessions()
            elif command.strip().lower() == "agenda":
                self.show_agenda()
            elif command.strip().lower() == "help":
                self.show_help()
            elif command.strip().lower() == "rooms":
                self.show_rooms()
            elif command.strip().startswith("notify_room"):
                args = command[len("notify_room"):].strip().split(" ", 1)
                if len(args) == 2:
                    room_index, message = args
                    room_index = room_index.strip()
                    if room_index in self.room_index_mapping:
                        irc_room = self.room_index_mapping[room_index]

                        self.connection.privmsg(irc_room, f"[Announcement] {message}")
                        print(f"[IRC] Notified room {irc_room}: {message}")
                    else:
                        print(f"Room index '{room_index}' not found in room mapping.")
                else:
                    print("Usage: notify_room <room_name> <message>")
            elif command.strip().lower() == "quit":
                self.quit_bot()
            elif command.strip().lower() == "today":
                self.show_today_agenda()
            elif command.strip().lower() == "time":
                self.show_current_time()
            elif command.strip().startswith("speed"):
                args = command[len("speed"):].strip()
                self.increase_speed(args)

    def show_current_time(self):
        current_time = self.debug_current_time or datetime.datetime.now()
        print(f"Current date and time: {current_time}")

    def show_help(self):
        print("Available commands:")
        print("  reload - Reload the schedule from the file or API")
        print("  now - Show currently running sessions")
        print("  agenda - Print the entire agenda per room")
        print("  today - Show today's agenda")
        print("  time - Display the current date and time")
        print("  speed [factor] - Set the speed of the simulation (e.g., 'speed 10' for 10 times faster)")
        print("  quit - Stop the program and let the bot leave the rooms with a random hacker quote")
        print("  set_start_time [YYYY-MM-DD HH:MM] - Set a start date and time for simulation")
        print("  notify_room <room_index> <message> - Send a message to a specified IRC room by index")
        print("  rooms - List available IRC rooms")
        print("  help - Show this help message")

    def show_agenda(self):
        if not self.schedule:
            print("No agenda available.")
            return
        print("Agenda:")
        for day in self.schedule:
            day_date = day['date']
            print(f"Date: {day_date}")
            for room, talks in day['rooms'].items():
                print(f"  Room: {room}")
                for talk in talks:
                    title = talk['title']
                    speaker = talk['persons'][0]['public_name'] if talk.get('persons') else 'Unknown Speaker'
                    start_time = talk['start']
                    print(f"    '{title}' by {speaker} at {start_time}")

    def show_today_agenda(self):
        current_date = (self.debug_current_time or datetime.datetime.now()).date()
        print(f"Agenda for today ({current_date}):")
        agenda_found = False
        for day in self.schedule:
            day_date = datetime.datetime.strptime(day['date'], "%Y-%m-%d").date()
            if day_date == current_date:
                agenda_found = True
                for room, talks in day['rooms'].items():
                    print(f"  Room: {room}")
                    for talk in talks:
                        title = talk['title']
                        speaker = talk['persons'][0]['public_name'] if talk.get('persons') else 'Unknown Speaker'
                        start_time = talk['start']
                        print(f"    '{title}' by {speaker} at {start_time}")
        if not agenda_found:
            print("No agenda found for today.")

    def quit_bot(self):
        with open('quotes.txt', 'r') as f:
            hacker_quotes = [line.strip() for line in f.readlines()]
        quit_message = random.choice(hacker_quotes)
        print(f"[IRC] Quitting with message: {quit_message}")
        for irc_room in self.room_mapping.values():
            self.connection.part(irc_room, quit_message)
        self.connection.quit(quit_message)
        self.running = False  # Stop the main loop
        sys.exit(0)  # Ensure the program exits

    def increase_speed(self, factor):
        try:
            self.simulation_speed = int(factor)
            print(f"Simulation speed set to: {self.simulation_speed}")
        except ValueError:
            print("Invalid speed factor. Please provide an integer value.")

    def show_current_sessions(self):
        current_time = self.debug_current_time or datetime.datetime.now()
        currently_running_sessions = []

        for day in self.schedule:
            day_date = day['date']
            for room, talks in day['rooms'].items():
                for i, talk in enumerate(talks):
                    talk_datetime_str = f"{day_date} {talk['start']}"
                    talk_datetime = datetime.datetime.strptime(talk_datetime_str, "%Y-%m-%d %H:%M")
                    duration_str = talk.get('duration', '60')
                    try:
                        if ':' in duration_str:
                            hours, minutes = map(int, duration_str.split(':'))
                            duration = hours * 60 + minutes
                        else:
                            duration = int(duration_str)
                    except ValueError:
                        duration = 60  # Default to 60 minutes if parsing fails
                    talk_end_datetime = talk_datetime + datetime.timedelta(minutes=duration)

                    if talk_datetime <= current_time < talk_end_datetime:
                        title = talk['title']
                        speaker = talk['persons'][0]['public_name'] if talk.get('persons') else 'Unknown Speaker'
                        currently_running_sessions.append(f"'{title}' by {speaker} in {room}")

        if currently_running_sessions:
            print("Currently running sessions:")
            for session in currently_running_sessions:
                print(session)
        else:
            print("No sessions are currently running.")

    def on_welcome(self, connection, event):
        # Register the nickname with NickServ
        connection.privmsg('NickServ', f'identify {self.nickserv_password}')
        print("[IRC] Sent NickServ identification message.")
        self.connection = connection
        for irc_room in self.room_mapping.values():
            connection.join(irc_room)
            print(f"[IRC] Joined IRC room: {irc_room}")  # Debug output
        # Start the schedule announcer loop in a new thread
        threading.Thread(target=self.announce_schedule, daemon=True).start()

    def announce_schedule(self):
        def get_irc_room(room_name):
            irc_room = self.room_mapping.get(room_name)
            if irc_room:
                return irc_room
            else:
                print(f"Room '{room_name}' not found in room mapping.")
                return None


        def create_irc_room(talk_id, title, event_type):
            prefix = event_type.lower()
            irc_room_name = f"#{prefix}-{talk_id}"
            self.connection.join(irc_room_name, key='')
            self.connection.mode(irc_room_name, '+PH 100:1440')
            self.connection.topic(irc_room_name, f"{title}")
            print(f"[IRC] Created and set topic for room: {irc_room_name}")
        while self.running:
            if self.debug_current_time:
                self.debug_current_time += datetime.timedelta(seconds=self.simulation_speed)

            if self.simulating and self.debug_current_time:
                self.debug_current_time += datetime.timedelta(seconds=self.simulation_speed)
            current_time = self.debug_current_time or datetime.datetime.now()
            for day in self.schedule:
                day_date = day['date']
                for room, talks in day['rooms'].items():
                    for i, talk in enumerate(talks):
                        talk_datetime_str = f"{day_date} {talk['start']}"
                        talk_datetime = datetime.datetime.strptime(talk_datetime_str, "%Y-%m-%d %H:%M")
                        duration_str = talk.get('duration', '60')
                        try:
                            if ':' in duration_str:
                                hours, minutes = map(int, duration_str.split(':'))
                                duration = hours * 60 + minutes
                            else:
                                duration = int(duration_str)
                        except ValueError:
                            duration = 60  # Default to 60 minutes if parsing fails
                        talk_end_datetime = talk_datetime + datetime.timedelta(minutes=duration)
                        talk_id = f"{talk['id']}"  # Unique identifier for each talk

                        # Determine if it's a talk or a workshop/training
                        if room == "Europe - Main Room":
                            event_type = "Talk"
                        else:
                            event_type = "Workshop/Training"

                        # Announce 5 minutes before the event starts
                        if (current_time >= (talk_datetime - datetime.timedelta(minutes=5)) and current_time < talk_datetime
                                and talk_id not in self.announced_talks):
                            # Create IRC room asynchronously
                            threading.Thread(target=create_irc_room, args=(talk['id'], talk['title'], event_type), daemon=True).start()
                            title = talk['title']
                            speaker = talk['persons'][0]['public_name'] if talk.get('persons') else 'Unknown Speaker'
                            talk_url = talk.get('url', 'No URL available')
                            irc_dedicated_room = f"#{event_type.lower()}-{talk['id']}"
                            irc_room = self.get_irc_room(room)
                            message = f"Upcoming {event_type}: '{title}' by {speaker} at {talk['start']} in {room} in 5 minutes | More info: {talk_url} | Dedicated IRC Room for this session: {irc_dedicated_room}"
                            self.connection.privmsg(irc_room, f"[Announcement] {message}")
                            print(f"[IRC] Announced: {message} in channel: {irc_room}")  # Debug output
                            self.announced_talks.add(talk_id)

                        # Announce when the event starts (within a 1-minute window)
                        if (talk_datetime <= current_time < (talk_datetime + datetime.timedelta(minutes=1))
                                and talk_id not in self.started_talks):
                            title = talk['title']
                            speaker = talk['persons'][0]['public_name'] if talk.get('persons') else 'Unknown Speaker'
                            talk_url = talk.get('url', 'No URL available')
                            irc_dedicated_room = f"#{event_type.lower()}-{talk['id']}"
                            irc_room = self.get_irc_room(room)
                            start_message = f"Session begins: '{title}' by {speaker} in {room} | More info: {talk_url} | Dedicated IRC Room for this session: {irc_dedicated_room}"
                            self.connection.privmsg(irc_room, f"[Announcement] {start_message}")
                            print(f"[IRC] Announced: {start_message} in channel: {irc_room}")  # Debug output
                            self.started_talks.add(talk_id)

                        # Announce when the event ends (within a 1-minute window)
                        if (talk_end_datetime <= current_time < (talk_end_datetime + datetime.timedelta(minutes=1))
                                and talk_id not in self.ended_talks):
                            title = talk['title']
                            talk_url = talk.get('url', 'No URL available')
                            irc_dedicated_room = f"#{event_type.lower()}-{talk['id']}"
                            irc_room = self.get_irc_room(room)
                            end_message = f"Session ends: '{title}' in {room} | More info: {talk_url} | Dedicated IRC Room for this session: {irc_dedicated_room}"
                            self.connection.privmsg(irc_room, f"[Announcement] {end_message}")
                            print(f"[IRC] Announced: {end_message} in channel: {irc_room}")  # Debug output
                            self.ended_talks.add(talk_id)
            time.sleep(1 / self.simulation_speed)  # Adjust sleep for simulation speed

if __name__ == "__main__":
    bot = ScheduleAnnouncer('config.ini', json_file=None)
    bot.start()

    # Keep the main thread running to avoid immediate exit
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        bot.quit_bot()
