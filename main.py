import logging
from datetime import date

import flet as ft

import database as db
from backup import BackupError, describe_import, describe_result, load_backup
from helpers import config_options, filter_workouts, parse_count
from timers import TimerPanel

log = logging.getLogger(__name__)


def main(page: ft.Page):
    # Page config
    page.title = "Kettlebell Bible"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.LIGHT_BLUE_ACCENT)

    # Create/upgrade the database (and load the bundled workouts on first run)
    db.init_db()

    # load the data
    full_data = db.fetch_all_workouts()

    # The timer panel of the workout currently on screen (stopped when we leave it)
    active_timer_stop = None

    # Used by the rest timer to buzz when time is up (the app must hold on to it)
    haptic = ft.HapticFeedback()

    # Keeps the screen on while a timer runs (the app has to hold on to this service)
    wakelock = ft.Wakelock()
    wake_state = {"on": False}

    async def apply_wakelock(on):
        try:
            await (wakelock.enable() if on else wakelock.disable())
        except Exception as ex:  # e.g. not supported here; timers still work
            log.warning("Couldn't change the screen wake lock: %s", ex)

    def keep_awake(on):
        if wake_state["on"] != on:
            wake_state["on"] = on
            page.run_task(apply_wakelock, on)

    # Container for our list of workouts
    # Empty column for now
    workout_column = ft.Column()

    # --------------------------------HELPER FUNCTIONS----------------------------------

    # Takes in a list of data and turn them into cards for the app
    def render_workouts(data_to_show):
        # Ensure the list is clear
        workout_column.controls.clear()
        # Add Workout Cards to the application
        for workout in data_to_show:

            def go_to_detail(e, w=workout):
                show_detail(w)

            # Simple Homepage Tiles
            tile = ft.ListTile(
                leading=ft.Icon(ft.Icons.FITNESS_CENTER),
                title=ft.Text(
                    workout["title"] or "Untitled", weight=ft.FontWeight.BOLD
                ),
                subtitle=ft.Row(
                    [
                        ft.Chip(
                            label=ft.Text(workout["config"] or "General"),
                            color=ft.Colors.PRIMARY_CONTAINER,
                            height=30,
                        ),
                        ft.Chip(
                            label=ft.Text(workout["type"] or "Workout"),
                            color=ft.Colors.SECONDARY_CONTAINER,
                            height=30,
                        ),
                    ]
                ),
                on_click=go_to_detail,
                trailing=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14),
            )
            # Add the card to the list of workouts
            workout_column.controls.append(ft.Card(content=tile))
        # Refresh
        page.update()

    # Re-draws the list using whatever the dropdown and search box currently say
    def apply_filters(e=None):
        render_workouts(
            filter_workouts(full_data, config_dropdown.value, searchbar.value)
        )

    # Keeps the dropdown in step with the equipment actually used in the library
    def refresh_filter_options():
        choices = ["All"] + config_options(full_data)
        config_dropdown.options = [ft.dropdown.Option(choice) for choice in choices]
        if config_dropdown.value not in choices:
            config_dropdown.value = "All"

    # Re-reads the database, then redraws the list with the active filters applied
    def reload_data():
        nonlocal full_data
        full_data = db.fetch_all_workouts()
        refresh_filter_options()
        apply_filters()

    def stop_active_timer():
        nonlocal active_timer_stop
        if active_timer_stop is not None:
            active_timer_stop()
            active_timer_stop = None

    # Pushes a workout's detail page on top of the list (or swaps the current one)
    def show_detail(workout, replace=False):
        stop_active_timer()
        if replace and len(page.views) > 1:
            page.views.pop()
        page.views.append(view_workout_details(workout))
        page.update()

    # Leaves the detail page and returns to the list
    def close_detail():
        stop_active_timer()
        if len(page.views) > 1:
            page.views.pop()

    def view_pop(e):
        close_detail()
        page.update()

    page.on_view_pop = view_pop

    def close_dialog(e):
        dlg_modal.open = False
        page.update()

    def validate_new(e):
        # If there is a value for title, allow save
        save_btn.disabled = not new_title.value.strip()
        dlg_modal.update()

    def save_new_workout(e):
        # Create dictionary to be added to
        new_workout = {
            "title": new_title.value.strip(),
            "type": new_type.value,
            "config": new_config.value,
            "rest": new_rest.value,
            "content": new_content.value,
            "rounds": new_rounds.value,
        }

        # Add to Database
        db.add_workouts(new_workout)

        # Clear out the text fields for the next entry
        new_title.value = ""
        new_type.value = ""
        new_config.value = ""
        new_rest.value = ""
        new_content.value = ""
        new_rounds.value = ""

        # Relock save button
        save_btn.disabled = True

        # Show everything again so the new workout is visible, not hidden by a filter
        config_dropdown.value = "All"
        searchbar.value = ""

        # Close Dialog and Refresh
        dlg_modal.open = False
        reload_data()
        page.update()

    def validate_edit(e):
        # If there is a title, enable save button
        save_btn_edit.disabled = not edit_title.value.strip()
        edit.update()

    def update_workout(e):
        # Retrieves the specific workout dictionary being edited
        workout_to_edit = edit.data

        # Create a dictionary of the new values
        updated_values = {
            "title": edit_title.value.strip(),
            "type": edit_type.value,
            "config": edit_config.value,
            "rest": edit_rest.value,
            "content": edit_content.value,
            "rounds": edit_rounds.value,
        }

        # Update in Database
        # Use the id that came from the database when we load the app
        db.update_workout(workout_to_edit["id"], updated_values)

        # Refresh the homepage (keeps the current filter and search)
        reload_data()

        # Update the detail view if it's currently open
        if len(page.views) > 1:
            # Find the specific updated workout from our new list
            new_version = next(
                (w for w in full_data if w["id"] == workout_to_edit["id"]), None
            )
            if new_version:
                show_detail(new_version, replace=True)
            else:
                close_detail()

        # Refresh UI
        edit.open = False
        page.update()

    def permanent_delete(e):
        # Pull the workout from a 'waiting room'
        workout_to_delete = confirm_dlg.data

        # Perform the delete
        db.delete_workout(workout_to_delete["id"])

        # Refresh the homepage (keeps the current filter and search)
        reload_data()

        # Go back to the home page after deletion
        close_detail()

        # Close confirm dialog
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

    async def export_backup(e):
        # Writes every workout to a JSON file the user picks (Drive, Downloads, etc.)
        try:
            saved = await ft.FilePicker().save_file(
                dialog_title="Export workouts",
                file_name=f"kettlebell-bible-{date.today().isoformat()}.json",
                src_bytes=db.export_json().encode("utf-8"),
            )
        except Exception as ex:
            snack(f"Export failed: {ex}")
            return
        if saved is not None:
            snack("Backup exported")

    # Shows a short message at the bottom of the screen
    def snack(message):
        page.show_dialog(ft.SnackBar(ft.Text(message)))

    # The backup waiting for the user's OK in the import dialog
    pending_import = {"workouts": [], "counts": {}}

    # The workouts the user has ticked to bring back from the deleted ones
    def ticked_restores():
        return [box.data for box in restore_column.controls if box.value]

    # The Import button only works when there is something it would actually do
    def refresh_import_button():
        counts = pending_import["counts"]
        import_btn.disabled = not (
            counts["added"] or counts["updated"] or ticked_restores()
        )
        import_dlg.update()

    async def import_backup(e):
        # Reads a backup file, shows what would change, and waits for confirmation
        try:
            files = await ft.FilePicker().pick_files(dialog_title="Import workouts")
        except Exception as ex:
            snack(f"Import failed: {ex}")
            return
        if not files:  # Picker was closed without choosing a file
            return
        if not files[0].path:
            snack("This device didn't let the app open that file.")
            return

        try:
            backup = load_backup(files[0].path)
            counts = db.import_workouts(backup.workouts, dry_run=True)
        except BackupError as ex:
            snack(str(ex))
            return
        except Exception as ex:
            snack(f"Import failed: {ex}")
            return

        if not (counts["added"] or counts["updated"] or counts["deleted_here"]):
            snack(
                "Nothing to import: your library already has everything in this file."
            )
            return

        total = len(backup.workouts)
        header = f"This backup has {total} workout{'' if total == 1 else 's'}"
        if backup.exported_at:
            header += f" (exported {backup.exported_at[:10]})"
        lines = [header + ":", ""]
        lines += ["• " + line for line in describe_import(counts, backup)]
        if counts["deleted_here"]:
            lines.append("")
            if counts["added"] or counts["updated"]:
                lines.append("Workouts you deleted stay deleted unless you tick them.")
            else:
                lines.append(
                    "There's nothing new to import. Tick a deleted workout to bring "
                    "it back, or Cancel to leave everything as it is."
                )
        import_summary.value = "\n".join(lines)
        # One checkbox per deleted workout so each can be kept deleted or brought back
        restore_column.controls = [
            ft.Checkbox(
                label=deleted["title"],
                data=deleted["uuid"],
                value=False,
                on_change=lambda e: refresh_import_button(),
            )
            for deleted in counts["deleted"]
        ]
        restore_heading.visible = bool(counts["deleted"])
        pending_import.update(workouts=backup.workouts, counts=counts)
        refresh_import_button()
        import_dlg.open = True
        page.update()

    def confirm_import(e):
        import_dlg.open = False
        try:
            result = db.import_workouts(
                pending_import["workouts"], restore=ticked_restores()
            )
        except Exception as ex:
            page.update()
            snack(f"Import failed: {ex}")
            return
        # Show everything so imported workouts aren't hidden by a filter
        config_dropdown.value = "All"
        searchbar.value = ""
        reload_data()
        page.update()
        snack(describe_result(result))

    def close_import_dialog(e):
        import_dlg.open = False
        page.update()

    def view_workout_details(workout):
        # Returns a 'View' object
        nonlocal active_timer_stop

        # Each workout page gets its own counter and timers, so nothing carries over
        rounds_done = ft.TextField(
            value="0",
            text_align=ft.TextAlign.CENTER,
            width=50,
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=ft.NumbersOnlyInputFilter(),
        )

        timer = TimerPanel(page, keep_awake, haptic, workout["rest"])
        active_timer_stop = timer.stop

        def change_rounds(amount):
            rounds_done.value = str(max(0, parse_count(rounds_done.value) + amount))
            rounds_done.update()
            # Finishing a round starts the rest countdown (needs a readable rest time)
            if amount > 0 and auto_rest.value and timer.has_rest_preset:
                timer.start_rest()

        def save_auto_rest(e):
            db.set_setting("auto_rest", "1" if auto_rest.value else "0")

        auto_rest = ft.Switch(
            label="Auto-start rest timer",
            value=db.get_setting("auto_rest", "1") == "1",
            on_change=save_auto_rest,
        )

        # Edit/Delete Logic
        def handle_edit(e):
            # Populates text boxes with current data
            edit_title.value = workout["title"]
            edit_type.value = workout["type"]
            edit_config.value = workout["config"]
            edit_rest.value = workout["rest"]
            edit_content.value = workout["content"]
            edit_rounds.value = workout["rounds"]
            # Only allow saving when there is a title to save
            save_btn_edit.disabled = not edit_title.value.strip()
            # Store the workout reference in the 'waiting room' for updating
            edit.data = workout
            # Open the dialog box
            edit.open = True
            page.update()

        def handle_delete(e):
            confirm_dlg.data = workout
            confirm_dlg.open = True
            page.update()

        # Only show the rounds/rest line for the parts this workout actually has
        rounds_rest = []
        if workout["rounds"]:
            rounds_rest.append(
                ft.Text(workout["rounds"], size=16, color=ft.Colors.BLUE)
            )
        if workout["rounds"] and workout["rest"]:
            rounds_rest.append(ft.VerticalDivider())
        if workout["rest"]:
            rounds_rest.append(ft.Text(workout["rest"], size=16, color=ft.Colors.RED))

        workout_details = [
            ft.Text(
                "THE WORKOUT",
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.OUTLINE,
            ),
            ft.Text(
                workout["content"],
                size=16,
                selectable=True,
            ),
            ft.Divider(
                height=40,
                color=ft.Colors.OUTLINE_VARIANT,
            ),
        ]
        if rounds_rest:
            workout_details += [
                ft.Row(rounds_rest, alignment=ft.MainAxisAlignment.SPACE_AROUND),
                ft.Divider(height=40),
            ]
        workout_details.append(
            # Action Buttons
            ft.Row(
                [
                    ft.Button(
                        "Edit",
                        icon=ft.Icons.EDIT,
                        on_click=handle_edit,
                    ),
                    ft.Button(
                        "Delete",
                        icon=ft.Icons.DELETE_FOREVER,
                        color=ft.Colors.ERROR,
                        on_click=handle_delete,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            )
        )

        config_and_type = " • ".join(
            part for part in (workout["config"], workout["type"]) if part
        )

        # Page Layout
        return ft.View(
            route="/workout_detail",
            scroll=ft.ScrollMode.ADAPTIVE,
            controls=[
                ft.SafeArea(
                    content=ft.Column(
                        [
                            ft.AppBar(title=ft.Text(workout["title"] or "Untitled")),
                            # Header Content
                            ft.Container(
                                bgcolor=ft.Colors.PRIMARY_CONTAINER,
                                padding=20,
                                border_radius=10,
                                content=ft.SelectionArea(
                                    content=ft.Column(
                                        [
                                            ft.Text(
                                                "CONFIGURATION",
                                                size=10,
                                                weight=ft.FontWeight.BOLD,
                                                color=ft.Colors.ON_PRIMARY_CONTAINER,
                                            ),
                                            ft.Row(
                                                [
                                                    ft.Icon(
                                                        ft.Icons.FITNESS_CENTER,
                                                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                                                    ),
                                                    ft.Text(
                                                        config_and_type or "General",
                                                        size=18,
                                                        weight=ft.FontWeight.BOLD,
                                                        color=ft.Colors.ON_PRIMARY_CONTAINER,
                                                    ),
                                                ]
                                            ),
                                        ]
                                    )
                                ),
                            ),
                            # Workout Content
                            ft.Container(
                                padding=20,
                                content=ft.SelectionArea(
                                    content=ft.Column(workout_details)
                                ),
                            ),
                            # Round Counter
                            ft.Container(
                                margin=ft.Margin.only(top=10, bottom=10),
                                content=ft.Column(
                                    [
                                        ft.Row(
                                            [
                                                ft.Text(
                                                    "Rounds Completed:",
                                                    weight=ft.FontWeight.BOLD,
                                                ),
                                                ft.Container(width=20),
                                                ft.IconButton(
                                                    ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                                    on_click=lambda e: change_rounds(
                                                        -1
                                                    ),
                                                    icon_color=ft.Colors.RED_400,
                                                ),
                                                rounds_done,
                                                ft.IconButton(
                                                    ft.Icons.ADD_CIRCLE_OUTLINE,
                                                    on_click=lambda e: change_rounds(1),
                                                    icon_color=ft.Colors.GREEN_400,
                                                ),
                                            ],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                        ),
                                        ft.Row(
                                            [auto_rest],
                                            alignment=ft.MainAxisAlignment.CENTER,
                                        ),
                                        # Timers
                                        ft.Divider(),
                                        timer.layout,
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                ),
                                width=float("inf"),
                            ),
                        ]
                    )
                )
            ],
        )

    # ---------- UI SETUP ----------

    # INPUT FIELDS FOR ADDING WORKOUTS
    new_title = ft.TextField(label="Workout Title", on_change=validate_new)
    new_type = ft.TextField(label="Type (Complex, Workout, EMOM, etc.)")
    new_config = ft.TextField(label="Equipment Used")
    new_rest = ft.TextField(label="Rest Between Rounds")
    new_content = ft.TextField(label="Workout Details/Exercises", multiline=True)
    new_rounds = ft.TextField(label="Rounds")
    # INPUT FIELDS FOR EDITING WORKOUTS
    edit_title = ft.TextField(label="Workout Title", on_change=validate_edit)
    edit_type = ft.TextField(label="Type (Complex, Workout, EMOM, etc.)")
    edit_config = ft.TextField(label="Equipment Used")
    edit_rest = ft.TextField(label="Rest Between Rounds")
    edit_content = ft.TextField(label="Workout Details/Exercises", multiline=True)
    edit_rounds = ft.TextField(label="Rounds")

    # Create dedicated save button for adding workout
    save_btn = ft.TextButton("Save", on_click=save_new_workout, disabled=True)
    # Create dedicated save button for editing workouts
    save_btn_edit = ft.TextButton("Save", on_click=update_workout, disabled=True)
    # Defines the 'Add Workout' dialog window
    dlg_modal = ft.AlertDialog(
        modal=True,
        title=ft.Text("Add New Workout"),
        content=ft.Column(
            [new_title, new_type, new_config, new_rest, new_content, new_rounds],
            scroll=ft.ScrollMode.ADAPTIVE,
        ),
        actions=[
            save_btn,
            ft.TextButton("Cancel", on_click=close_dialog),
        ],
        actions_padding=ft.Padding.only(right=20, top=40, bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Defines the 'Confirm Delete' dialog window
    confirm_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Please Confirm Delete"),
        content=ft.Text("Are you sure you want to delete?"),
        actions=[
            ft.TextButton("Yes, Delete", on_click=permanent_delete),
            ft.TextButton("No", on_click=close_confirm),
        ],
        actions_padding=ft.Padding.only(right=20, top=40, bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Defines the 'Import Backup' dialog window
    import_summary = ft.Text()
    restore_heading = ft.Text(
        "Deleted since this backup was made (tick to bring back):",
        weight=ft.FontWeight.BOLD,
        visible=False,
    )
    restore_column = ft.Column(tight=True)
    import_btn = ft.TextButton("Import", on_click=confirm_import, disabled=True)
    import_dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Import Backup"),
        content=ft.Column(
            [import_summary, restore_heading, restore_column],
            tight=True,
            scroll=ft.ScrollMode.ADAPTIVE,
        ),
        actions=[import_btn, ft.TextButton("Cancel", on_click=close_import_dialog)],
        actions_padding=ft.Padding.only(right=20, top=40, bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Defines the 'Edit Workout' dialog window
    edit = ft.AlertDialog(
        modal=True,
        title=ft.Text("Edit Workout"),
        content=ft.Column(
            [edit_title, edit_type, edit_config, edit_rest, edit_content, edit_rounds],
            scroll=ft.ScrollMode.ADAPTIVE,
        ),
        actions=[save_btn_edit, ft.TextButton("Cancel", on_click=close_edit_dialog)],
        actions_padding=ft.Padding.only(right=20, top=40, bottom=10),
        actions_alignment=ft.MainAxisAlignment.END,
    )

    # Define the Dropdown Menu (options are filled in from the library's equipment)
    # on_select fires when a choice is made, on_text_change is kept from the old
    # version in case a device reports selections that way. Running twice is harmless.
    config_dropdown = ft.Dropdown(
        width=200,
        label="Filter",
        value="All",
        options=[ft.dropdown.Option("All")],
        on_select=apply_filters,
        on_text_change=apply_filters,
    )
    refresh_filter_options()

    # Define the Search Bar
    searchbar = ft.TextField(
        label="Search",
        width=300,
        prefix_icon=ft.Icons.SEARCH_OUTLINED,
        on_change=apply_filters,
    )

    # Opens the dialog on startup (hidden by default)
    page.overlay.append(dlg_modal)
    page.overlay.append(confirm_dlg)
    page.overlay.append(edit)
    page.overlay.append(import_dlg)

    # Homepage Setup Config
    home_view = ft.View(
        route="/",
        controls=[
            ft.SafeArea(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "Kettlebell Bible",
                                    size=30,
                                    weight=ft.FontWeight.W_300,
                                ),
                                ft.PopupMenuButton(
                                    icon=ft.Icons.MORE_VERT,
                                    tooltip="Backup",
                                    items=[
                                        ft.PopupMenuItem(
                                            content="Export backup",
                                            icon=ft.Icons.FILE_DOWNLOAD,
                                            on_click=export_backup,
                                        ),
                                        ft.PopupMenuItem(
                                            content="Import backup",
                                            icon=ft.Icons.FILE_UPLOAD,
                                            on_click=import_backup,
                                        ),
                                    ],
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Row([config_dropdown, searchbar]),
                        ft.Divider(),
                        ft.Container(content=workout_column, expand=True),
                    ]
                )
            )
        ],
        # Add Button Definition
        floating_action_button=ft.FloatingActionButton(
            icon=ft.Icons.NOTE_ADD, on_click=open_dialog
        ),
    )
    page.views.clear()
    page.views.append(home_view)
    page.scroll = ft.ScrollMode.AUTO  # can scroll if the list is long

    # Initial Render
    apply_filters()


# Run the app
ft.run(main)
