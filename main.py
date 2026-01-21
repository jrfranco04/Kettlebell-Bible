import flet as ft
import json
import threading
import time



def main(page: ft.Page):
    #Page config
    page.title = "Kettlebell Bible"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.LIGHT_BLUE_ACCENT)
    page.scroll = "adaptive" #can scroll if the list is long

    def view_pop(view):
        page.views.pop() # Removes top card
        page.update()
    page.on_view_pop = view_pop

    #load the data
    with open('workouts.json', 'r') as file:
        full_data = json.load(file)

    #Container for our list of workouts
    #Empty column for now
    workout_column = ft.Column()

    #--------------------------------HELPER FUNCTIONS----------------------------------

    #Takes in a list of data and turn them into cards for the app
    def render_workouts(data_to_show):
        #Ensure the list is clear
        workout_column.controls.clear()
        #Add Workout Cards to the application
        for workout in data_to_show:
            def go_to_detail(e, w=workout):
                page.views.append(view_workout_details(w)) #Adds the card to the stack of cards
                page.update()
            #Simple Homepage Tiles
            tile = ft.ListTile(
                leading=ft.Icon(ft.Icons.FITNESS_CENTER),
                title=ft.Text(workout.get('title', 'Untitled'), weight=ft.FontWeight.BOLD),
                subtitle=ft.Row([
                    ft.Chip(
                        label=ft.Text(workout.get('config', 'General')),
                        color=ft.Colors.PRIMARY_CONTAINER,
                        height=30,
                    ),
                    ft.Chip(
                        label=ft.Text(workout.get('type', 'Workout')),
                        color=ft.Colors.SECONDARY_CONTAINER,
                        height=30,
                    ),
                ]),
                on_click=go_to_detail,
                trailing=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14)
            )
            workout_card = ft.Card(
                content=tile,
                elevation=5,
                margin=ft.Margin.symmetric(vertical=10,horizontal=5)
            )
            #Add the card to the list of workouts
            workout_column.controls.append(ft.Card(content=tile))
        #Refresh
        page.update()

    def filter_change(e):
        #Default to all data shown
        filtered_data = full_data

        #Apply the dropdown filter
        selected = config_dropdown.value
        #Filter the list down to selected value
        if selected != 'All' and selected is not None:
            filtered_data = [w for w in full_data if selected in w.get('config', '')]

        #Apply the keyword filter
        search_text = searchbar.value.lower()
        if search_text:
            #Filter the list down by keyword
            filtered_data = [
                w for w in filtered_data
                if search_text in w.get('title', '').lower()
                or search_text in w.get('type', '').lower()
                or search_text in w.get('rest', '').lower()
                or search_text in w.get('rounds', '').lower()
            ]

        # Re-render with filtered data
        render_workouts(filtered_data)

    def close_dialog(e):
        dlg_modal.open = False
        page.update()

    def validate_new(e):
        # If there is a value for title, allow save
        if new_title.value:
            save_btn.disabled = False
        # If not, do not allow save
        else:
            save_btn.disabled = True
        dlg_modal.update()

    def save_new_workout(e):
        #Create dictionary to be added to
        new_workout = {
            'title': new_title.value,
            'type': new_type.value,
            'config': new_config.value,
            'rest': new_rest.value,
            'content': new_content.value,
            'rounds': new_rounds.value
        }

        #Add to local list (full_data)
        full_data.append(new_workout)

        #Save to JSON file (Permanent Storage)
        with open('workouts.json', 'w') as f:
            json.dump(full_data, f, indent=4)

        #Clear out the text fields for the next entry
        new_title.value = ''
        new_type.value = ''
        new_config.value = ''
        new_rest.value = ''
        new_content.value = ''
        new_rounds.value = ''

        # Relock save button
        save_btn.disabled=True

        #Close Dialog and Refresh
        dlg_modal.open = False
        render_workouts(full_data)
        page.update()

    def validate_edit(e):
        # If there is a title, enable save button
        if edit_title.value:
            save_btn_edit.disabled = False
        # If there is no title, disable save button
        else:
            save_btn_edit.disabled = True
        edit.update()

    def update_workout(e):
        #Retrieves the specific workout dictionary being edited
        workout_to_edit = edit.data

        #Update dictionary values
        workout_to_edit['title'] = edit_title.value
        workout_to_edit['type'] = edit_type.value
        workout_to_edit['config'] = edit_config.value
        workout_to_edit['rest'] = edit_rest.value
        workout_to_edit['content'] = edit_content.value
        workout_to_edit['rounds'] = edit_rounds.value

        #Save to file
        with open('workouts.json', 'w') as f:
            json.dump(full_data, f, indent=4)

        #Refresh the homepage
        render_workouts(full_data)

        #Hot Swap Data in the Card being viewed (real-time updates for edits to workouts)
        if len(page.views) > 1:
            page.views.pop() #Removes the old page
            fresh = view_workout_details(workout_to_edit) #Creates fresh card
            page.views.append(fresh) #Adds the new card

        #Refresh UI
        edit.open = False
        page.update()

    def permanent_delete(e):
        #Pull the workout from a 'waiting room'
        workout_to_delete = confirm_dlg.data

        #Perform the delete
        if workout_to_delete in full_data:
            full_data.remove(workout_to_delete)
            #Save to JSON file
            with open('workouts.json', 'w') as f:
                json.dump(full_data, f, indent=4)

            #Refresh UI
            render_workouts(full_data)

        #Close confirm dialog
        confirm_dlg.open = False
        page.update()

    def close_confirm(e):
        confirm_dlg.open = False
        page.update()

    def open_dialog(e):
        dlg_modal.open = True
        page.update()

    def close_edit_dialog(e):
        edit.open = False
        page.update()

    def view_workout_details(workout):
        # Returns a 'View' object
        #Edit/Delete Logic
        def handle_edit(e):
            # Populates text boxes with current data
            edit_title.value = workout.get('title', '')
            edit_type.value = workout.get('type', '')
            edit_config.value = workout.get('config', '')
            edit_rest.value = workout.get('rest', '')
            edit_content.value = workout.get('content', '')
            edit_rounds.value = workout.get('rounds', '')
            # Store the workout reference in the 'waiting room' for updating
            edit.data = workout
            # Open the dialog box
            edit.open = True
            page.update()
        def handle_delete(e):
            confirm_dlg.data = workout
            confirm_dlg.open=True
            page.update()

        #Page Layout
        return ft.View(
            route='/workout_detail',
            controls=[
                ft.SafeArea(
                    content=ft.Column([
                        ft.AppBar(title=ft.Text(workout.get('title', 'Untitled'))),
                        # Header Content
                        ft.Container(
                            bgcolor=ft.Colors.PRIMARY_CONTAINER,
                            padding=20,
                            border_radius=10,
                            content=ft.SelectionArea(
                                content=ft.Column([
                                    ft.Text('CONFIGURATION', size=10, weight=ft.FontWeight.BOLD,
                                            color=ft.Colors.ON_PRIMARY_CONTAINER),
                                    ft.Row([
                                        ft.Icon(ft.Icons.FITNESS_CENTER, color=ft.Colors.ON_PRIMARY_CONTAINER),
                                        ft.Text(f'{workout.get('config')} • {workout.get('type')}', size=18,
                                                weight=ft.FontWeight.BOLD, color=ft.Colors.ON_PRIMARY_CONTAINER),
                                    ]),
                                ])
                            )
                        ),
                        # Workout Content
                        ft.Container(
                            padding=20,
                            content=ft.SelectionArea(
                                content=ft.Column([
                                    ft.Text('THE WORKOUT', weight=ft.FontWeight.BOLD, color=ft.Colors.OUTLINE),
                                    ft.Text(workout.get('content'), size=16, selectable=True),

                                    ft.Divider(height=40, color=ft.Colors.OUTLINE_VARIANT),

                                    ft.Row([
                                        ft.Text(workout.get('rounds'), size=16, color=ft.Colors.BLUE),
                                        ft.VerticalDivider(),
                                        ft.Text(workout.get('rest'), size=16, color=ft.Colors.RED),
                                    ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
                                    ft.Divider(height=40),
                                    # Action Buttons
                                    ft.Row([
                                        ft.Button('Edit', icon=ft.Icons.EDIT, on_click=handle_edit),
                                        ft.Button('Delete', icon=ft.Icons.DELETE_FOREVER, color=ft.Colors.ERROR,
                                                  on_click=handle_delete),
                                    ], alignment=ft.MainAxisAlignment.CENTER)
                                ])
                            )
                        ),
                        # Stopwatch
                        ft.Container(

                            margin=ft.Margin.only(top=10, bottom=10),
                            content=create_stopwatch(page), alignment=ft.Alignment.CENTER
                            # This alignment doesn't do what I want it to right now...
                        ),
                    ])
                ),
            ]
        )

    #Internal Stopwatch
    def create_stopwatch(p):
        # [seconds, is_running]
        state = [0, False]
        # Stopwatch UI
        time_display = ft.Text('00:00', size=40, weight=ft.FontWeight.BOLD,font_family='monospace')
        # STOPWATCH LOGIC
        # Listener function to wait for a broadcast message from the stopwatch
        def on_tick(message):
            if message == 'tick':
                time_display.value = format_time(state[0])
                time_display.update()
        # Subscribe to the page's broadcast channel
        page.pubsub.subscribe(on_tick)

        def format_time(total_seconds):
            mins, sec = divmod(total_seconds, 60)
            return f'{mins:02d}:{sec:02d}'
        # Thread logic
        def update_timer():
            while state[1]: # While is_running is True (aka while timer is going)
                time.sleep(1)
                state[0] += 1
                # Shout 'tick' to the main page
                page.pubsub.send_all('tick')

        def start_timer(e):
            if not state[1]: # If not already running
                state[1] = True
                # Start thread in background
                threading.Thread(target=update_timer, daemon=True).start()
                # Toggle buttons defined below
                play_btn.visible = False
                pause_btn.visible = True
                page.update()

        def stop_timer(e):
            state[1] = False # Stops the timer
            play_btn.visible = True
            pause_btn.visible = False
            page.update()

        def reset_timer(e):
            state[1] = False # Stop
            state[0] = 0 # Reset timer numbers
            time_display.value = '00:00'
            play_btn.visible = True
            pause_btn.visible = False
            page.update()

        # Create Toggle Buttons
        play_btn = ft.IconButton(icon=ft.Icons.PLAY_ARROW, icon_size=30, on_click=start_timer, icon_color=ft.Colors.GREEN)
        pause_btn = ft.IconButton(icon=ft.Icons.PAUSE, icon_size=30, on_click=stop_timer, visible=False, icon_color=ft.Colors.AMBER)
        reset_btn = ft.IconButton(icon=ft.Icons.REPLAY_ROUNDED, icon_size=30, on_click=reset_timer,icon_color=ft.Colors.RED)

        # Return the UI Layout
        return ft.Container(
            border_radius=10,
            padding=10,
            content=ft.Column([
                time_display,
                ft.Divider(),
                ft.Row([play_btn,pause_btn,reset_btn]),
            ], alignment=ft.MainAxisAlignment.CENTER)
        )


    #---------- UI SETUP ----------

    #INPUT FIELDS FOR ADDING WORKOUTS
    new_title = ft.TextField(label='Workout Title', on_change=validate_new)
    new_type = ft.TextField(label='Type (Complex, Workout, EMOM, etc.)')
    new_config = ft.TextField(label='Equipment Used')
    new_rest = ft.TextField(label='Rest Between Rounds')
    new_content = ft.TextField(label='Workout Details/Exercises', multiline=True)
    new_rounds = ft.TextField(label='Rounds')
    #INPUT FIELDS FOR EDITING WORKOUTS
    edit_title = ft.TextField(label='Workout Title', on_change=validate_edit)
    edit_type = ft.TextField(label='Type (Complex, Workout, EMOM, etc.)')
    edit_config = ft.TextField(label='Equipment Used')
    edit_rest = ft.TextField(label='Rest Between Rounds')
    edit_content = ft.TextField(label='Workout Details/Exercises', multiline=True)
    edit_rounds = ft.TextField(label='Rounds')

    # Create dedicated save button for adding workout
    save_btn = ft.TextButton(
        'Save',
        on_click=save_new_workout,
        disabled=True
    )
    # Create dedicated save button for editing workouts
    save_btn_edit = ft.TextButton(
        'Save',
        on_click=update_workout,
        disabled=False
    )
    # Defines the 'Add Workout' dialog window
    dlg_modal = ft.AlertDialog(
        modal=True,
        title=ft.Text('Add New Workout'),
        content=ft.Column([
            new_title,
            new_type,
            new_config,
            new_rest,
            new_content,
            new_rounds
        ], height=400),
        actions=[
            save_btn,
            ft.TextButton('Cancel', on_click=close_dialog),
        ],
        actions_padding=ft.Padding.only(right=20,top=40,bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    #Defines the 'Confirm Delete' dialog window
    confirm_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text('Please Confirm Delete'),
        content=ft.Text('Are you sure you want to delete?'),
        actions=[
            ft.TextButton('Yes, Delete', on_click=permanent_delete),
            ft.TextButton('No', on_click=close_confirm),
        ],
        actions_padding=ft.Padding.only(right=20,top=40,bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    #Defines the 'Edit Workout' dialog window
    edit = ft.AlertDialog(
        modal=True,
        title=ft.Text('Edit Workout'),
        content=ft.Column([
            edit_title,
            edit_type,
            edit_config,
            edit_rest,
            edit_content,
            edit_rounds
        ], height=400),
        actions=[
            save_btn_edit,
            ft.TextButton('Cancel', on_click=close_edit_dialog)
        ],
        actions_padding=ft.Padding.only(right=20,top=40,bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    #Define the Dropdown Menu
    config_dropdown = ft.Dropdown(
        width=200,
        label="Filter",
        value="All",
        options = [
            ft.dropdown.Option('All'),
            ft.dropdown.Option('Single KB'),
            ft.dropdown.Option('Double KB'),
            ft.dropdown.Option('E2MOM'),
            ft.dropdown.Option('EMOM'),
            ft.dropdown.Option('Mace'),
        ],
        on_text_change=filter_change
    )

    #Define the Search Bar
    searchbar = ft.TextField(
        label='Search',
        width=300,
        prefix_icon=ft.Icons.SEARCH_OUTLINED,
        on_change=filter_change
    )

    #Opens the dialog on startup (hidden by default)
    page.overlay.append(dlg_modal)
    page.overlay.append(confirm_dlg)
    page.overlay.append(edit)

    #Homepage Setup Config
    home_view = ft.View(
        route='/',
        controls=[
            ft.SafeArea(
                content=ft.Column([
                    ft.Text('Kettlebell Bible', size=30, weight=ft.FontWeight.W_300),
                    ft.Row([config_dropdown, searchbar]),
                    ft.Divider(),
                    ft.Container(content=workout_column, expand=True)
                ])
            )
        ],
        #Add Button Definition
        floating_action_button = ft.FloatingActionButton(
            icon=ft.Icons.NOTE_ADD,
            on_click=open_dialog
        )
    )
    page.views.clear()
    page.views.append(home_view)
    page.scroll='auto'


    #Initial Render
    render_workouts(full_data)
    page.update()

#Run the app
ft.run(main)