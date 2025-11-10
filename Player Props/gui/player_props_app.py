#!/usr/bin/env python
# coding: utf-8

# In[6]:


from tkinter import *
from tkinter import messagebox, ttk
import PIL.Image as PILImage
from PIL import ImageTk
import requests
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from io import StringIO, BytesIO
from core.data_loader import *
from core.stats_utils import *
from core.stat_visualization import *
from core.monte_carlo_sim import *

team_stats = load_team_data()
player_stats = load_player_data()
team_list = list(team_stats['team'].unique())
pos_groups = ['QB','WR','TE','RB']
bettable_columns = ['passing_yards','passing_tds','completions','attempts','passing_interceptions','targets','receptions','receiving_yards','receiving_tds','carries','rushing_yards','rushing_tds']

# === GUI setup ===
root = Tk()
root.title("Run Model:")
root.geometry("670x400")

style = ttk.Style()
style.theme_use("clam")

style.configure("TButton",
                foreground="white",
                background="#444",
                padding=6,
                font=("Helvetica", 12, "bold"))

style.map("TButton",
          foreground=[("disabled", "#bbbbbb"), ("active", "white")],
          background=[("disabled", "#555555"), ("active", "#555555")])

# Split UI into two major columns
left_panel = Frame(root, bg="#2b2b2b")
left_panel.grid(row=0, column=0, padx=20, pady=20, sticky="n")

right_panel = Frame(root, bg="#2b2b2b")
right_panel.grid(row=0, column=1, padx=50, pady=20, sticky="n")

teams = ['select:'] + team_list

# Variables for dropdown selections
off_var = StringVar(value='select:')
def_var = StringVar(value='select:')
pos_var = StringVar(value='select:')
player_var = StringVar(value='select:')

off_trace_id = None
def_trace_id = None
pos_trace_id = None

def attach_traces():
    global off_trace_id, def_trace_id, pos_trace_id
    off_trace_id = off_var.trace_add("write", validate_selection)
    def_trace_id = def_var.trace_add("write", validate_selection)
    pos_trace_id = pos_var.trace_add("write", validate_selection)

# Placeholder for player dropdown
player_menu = None
player_label = None

# === Core logic ===
def validate_selection(*args):
    global player_menu, player_label

    # Prevent same team selection
    if off_var.get() != 'select:' and off_var.get() == def_var.get():
        messagebox.showerror("Invalid Selection", "You must select two different teams!")
        def_var.set('select:')  # reset second dropdown
    
    # enable position dropdown if both teams selected
    if off_var.get() != 'select:' and def_var.get() != 'select:':
        pos_menu.config(state='normal')
    else:
        pos_menu.config(state='disabled')
        pos_var.set('select:')

    # === Refresh player dropdown ===
    # Remove old player dropdown if it exists
    if player_menu:
        player_menu.grid_remove()
    if player_label:
        player_label.grid_remove()

    # Only show player dropdown once team + position are valid
    if (
        off_var.get() != 'select:' and
        def_var.get() != 'select:' and
        pos_var.get() != 'select:'):
        
        players = get_pos(off_var.get(), pos_var.get())
        
        if len(players) == 0:
            messagebox.showinfo("No Players Found", f"No {pos_var.get()}s found for {off_var.get()}")
            return

        player_label = Label(left_panel, text="Select Player:", bg="#2b2b2b", fg="white")
        player_label.grid(row=3, column=0, padx=10, pady=10, sticky="e")

        player_var.set('select:')
        player_menu = OptionMenu(left_panel, player_var, *(['select:'] + players))
        player_menu.grid(row=3, column=1, padx=10, pady=10)

        # Enable submit button
        submit_btn.config(state='normal')
    else:
        submit_btn.config(state='disabled')

attach_traces()  # call once at startup

# Submit function
def submit():
    if player_var.get() == 'select:':
        messagebox.showerror("Missing Selection", "Please select a player before running the model.")
        return

    player_name = player_var.get()

    # Create new result window
    result_window = Toplevel(root)
    result_window.title(f"Stats for {player_name}")
    result_window.geometry("1600x1050")
    result_window.configure(bg="#2b2b2b")

    # --- Scrollable window setup ---
    container = Frame(result_window, bg="#2b2b2b")
    container.pack(fill=BOTH, expand=True)

    # Canvas for scrollable content
    canvas = Canvas(container, bg="#2b2b2b", highlightthickness=0)
    canvas.pack(side=LEFT, fill=BOTH, expand=True)

    # --- Modern Scrollable Window Setup ---
    style = ttk.Style()
    style.theme_use("clam")  # Modern flat look
    style.configure("Vertical.TScrollbar",
                    gripcount=0,
                    background="#444",
                    darkcolor="#2b2b2b",
                    lightcolor="#2b2b2b",
                    troughcolor="#2b2b2b",
                    bordercolor="#2b2b2b",
                    arrowcolor="white")

    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview, style="Vertical.TScrollbar")
    scrollbar.pack(side=RIGHT, fill=Y)

    # Create a frame inside the canvas
    scrollable_frame = Frame(canvas, bg="#2b2b2b")
    scrollable_frame_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    # --- Fix: dynamically resize canvas when frame changes ---
    def _configure_scrollregion(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    scrollable_frame.bind("<Configure>", _configure_scrollregion)

    # --- Fix: make canvas width follow window resize ---
    def _configure_canvas(event):
        canvas.itemconfig(scrollable_frame_id, width=event.width)
    canvas.bind("<Configure>", _configure_canvas)

    # --- Improved cross-platform mousewheel scrolling ---
    def _on_mousewheel(event):
        if root.tk.call('tk', 'windowingsystem') == 'aqua':  # macOS
            canvas.yview_scroll(-1 * event.delta, "units")
        else:  # Windows / Linux
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

    # Windows and Mac use <MouseWheel>, Linux uses <Button-4/5>
    canvas.bind_all("<MouseWheel>", _on_mousewheel)       # Windows/Mac
    canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))  # Linux scroll up
    canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))   # Linux scroll down

   # === Get player data first ===
    df = find_player(player_name)
    player_name, summary = determine_stability(df)

    # --- Player Header Section ---
    header_frame = Frame(scrollable_frame, bg="#2b2b2b")
    header_frame.pack(pady=(15, 10))

    try:
        # Get the player's data
        df = find_player(player_name)

        # Safely extract headshot URL
        headshot_url = df['headshot_url'].dropna().unique()
        if len(headshot_url) > 0:
            headshot_url = headshot_url[0]
            #print(f"Loading headshot from URL: {headshot_url}")

            # Load and resize the image
            response = requests.get(headshot_url, timeout=10)
            response.raise_for_status()

            img_data = BytesIO(response.content)
            img = PILImage.open(img_data).convert("RGB").resize((200, 150), PILImage.LANCZOS)

            # Convert to a Tkinter-compatible image
            tk_img = ImageTk.PhotoImage(img)

            img_label = Label(header_frame, image=tk_img, bg="#2b2b2b")
            img_label.image = tk_img  # keep a reference to prevent garbage collection
            img_label.pack(side=LEFT, padx=10)
        else:
            raise ValueError("No headshot URL found")

    except Exception as e:
        print(f"Could not load player headshot: {e}")
        placeholder = Label(header_frame, text="[No Image]",
                            width=18, height=8, bg="#444", fg="white",
                            font=("Helvetica", 10))
        placeholder.pack(side=LEFT, padx=10)

    # Player name + info beside image
    info_frame = Frame(header_frame, bg="#2b2b2b")
    info_frame.pack(side=LEFT, padx=15)

    Label(info_frame, text=f"{player_name}",
          font=("Helvetica", 20, "bold"), bg="#2b2b2b", fg="white").pack(anchor="w")

    if 'position' in df.columns and 'team' in df.columns:
        pos = df['position'].iloc[0]
        team = df['team'].iloc[0]
        Label(info_frame, text=f"{pos} | {team}",
              font=("Helvetica", 14), bg="#2b2b2b", fg="#cccccc").pack(anchor="w")

    # ---- Stability Table ----
    Label(scrollable_frame, text="Most Consistent Stats (Lowest CV):",
          bg="#2b2b2b", fg="white", font=("Helvetica", 16, "italic")).pack()

    # Styling
    style = ttk.Style(result_window)
    style.configure("mystyle.Treeview",
                    highlightthickness=0, bd=0,
                    font=('Helvetica', 16),
                    background="#1e1e1e",
                    foreground="white",
                    fieldbackground="#1e1e1e")
    style.configure("mystyle.Treeview.Heading",
                    font=('Helvetica', 16, 'bold'),
                    background="#444", foreground="white")
    style.map('mystyle.Treeview', background=[('selected', '#3a86ff')])

    # === Side-by-Side Panel for Summary + Visualization ===
    top_split_frame = Frame(scrollable_frame, bg="#2b2b2b")
    top_split_frame.pack(fill=X, pady=(5, 25))

    # LEFT: Stats Summary
    left_stats_frame = Frame(top_split_frame, bg="#2b2b2b")
    left_stats_frame.pack(side=LEFT, padx=(80, 40), anchor="center")

    # Remove duplicate header — only a small caption
    Label(left_stats_frame, text="Consistency Summary",
          bg="#2b2b2b", fg="#bbbbbb",
          font=("Helvetica", 12, "italic")).pack(pady=(0, 10))

    columns = ('Stat', 'Mean', 'Std', 'CV')
    tree = ttk.Treeview(left_stats_frame, columns=columns, show='headings', style="mystyle.Treeview", height=8)
    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, anchor=CENTER, width=140)

    for stat, row in summary.iterrows():
        tree.insert('', END, values=(stat, row['mean'], row['std'], row['cv']))

    tree.pack(pady=5)

    # RIGHT: Visualization Panel
    right_viz_frame = Frame(top_split_frame, bg="#2b2b2b")
    right_viz_frame.pack(side=RIGHT, padx=20, anchor="n")

    Label(right_viz_frame, text="Visualize Player Stat:",
          bg="#2b2b2b", fg="white", font=("Helvetica", 14, "italic")).pack(pady=(0, 5))

    available_stats = [c for c in bettable_columns if c in df.columns]
    viz_var = StringVar(value="Select Stat")

    viz_menu = OptionMenu(right_viz_frame, viz_var, *available_stats)
    viz_menu.config(width=16)
    viz_menu.pack(pady=5)

    viz_canvas_frame = Frame(right_viz_frame, bg="#2b2b2b")
    viz_canvas_frame.pack()

    def update_visualization(*args):
        stat = viz_var.get()
        if stat == "Select Stat":
            return

        # Clear old plot
        for widget in viz_canvas_frame.winfo_children():
            widget.destroy()

        fig = visualize_stat(player_name, stat, def_var.get())
        canvas = FigureCanvasTkAgg(fig, master=viz_canvas_frame)
        canvas.draw()
        canvas.get_tk_widget().pack()

        plt.close(fig)  # prevent notebook popup

    viz_var.trace_add("write", update_visualization)

    # === Simulation Section ===
    sim_frame = Frame(scrollable_frame, bg="#2b2b2b")
    sim_frame.pack(pady=(15, 25))

    Label(sim_frame, text="Run Simulation:", bg="#2b2b2b", fg="white",
          font=("Helvetica", 16, "bold")).pack(anchor="w", padx=20)

    sim_inner = Frame(sim_frame, bg="#2b2b2b")
    sim_inner.pack(anchor="w", padx=20, pady=10)

    # Stat selection dropdown
    Label(sim_inner, text="Select Stat:", bg="#2b2b2b", fg="white").grid(row=0, column=0, padx=5, pady=5)
    sim_stat_var = StringVar(value="select:")
    OptionMenu(sim_inner, sim_stat_var, *available_stats).grid(row=0, column=1, padx=5, pady=5)

    # Line input
    Label(sim_inner, text="Target Line:", bg="#2b2b2b", fg="white").grid(row=0, column=2, padx=5, pady=5)
    line_entry = Entry(sim_inner, width=10)
    line_entry.grid(row=0, column=3, padx=5, pady=5)

    # Output label
    result_label = Label(sim_inner, text="Confidence: —", bg="#2b2b2b", fg="#cccccc",
                     font=("Helvetica", 12, "italic"))
    result_label.grid(row=1, column=0, columnspan=4, pady=10)

    # Run simulation function
    def run_simulation():
        stat_cat = sim_stat_var.get()
        line_val = line_entry.get()

        if stat_cat == "select:" or not line_val:
            messagebox.showwarning("Missing Input", "Please select a stat and enter a target line.")
            return
    
        try:
            line_val = float(line_val)
        except ValueError:
            messagebox.showerror("Invalid Input", "Target line must be a number.")
            return

        try:
            confidence = run_sim(player_name, def_var.get(), stat_cat, line_val)*100
            result_label.config(text=f"Confidence: {confidence:.1f}%", fg="#00cc66")
        except Exception as e:
            messagebox.showerror("Simulation Error", f"An error occurred while running simulation:\n{e}")
            result_label.config(text="Confidence: —", fg="red")

    # Run button
    Button(sim_inner, text="Run Simulation", command=run_simulation,
           bg="#3a86ff", fg="white", font=("Helvetica", 12, "bold")).grid(row=0, column=4, padx=10, pady=5)


    # ---- Week-by-week Table ----
    Label(scrollable_frame, text="Week-by-Week Performance:",
          bg="#2b2b2b", fg="white", font=("Helvetica", 16, "italic")).pack(pady=(10, 5))

    # Frame + Scrollbars for large tables
    frame = Frame(scrollable_frame)
    frame.pack(fill=BOTH, expand=True, padx=20, pady=10)

    if 'headshot_url' in df.columns:
        df = df.drop(columns=['player_display_name','headshot_url'])
    
    cols = list(df.columns)

    week_tree = ttk.Treeview(frame, columns=cols, show='headings', style="mystyle.Treeview")
    for col in cols:
        week_tree.heading(col, text=col)
        week_tree.column(col, anchor=CENTER, width=110)

    # --- Compute safe performance score ---
    existing_cols = [c for c in bettable_columns if c in df.columns]
    if not existing_cols:
        Label(scrollable_frame, text="No numeric stat columns found for this player.",
              bg="#2b2b2b", fg="red", font=("Helvetica", 16, "italic")).pack(pady=10)
        return

    df["performance_score"] = df[existing_cols].sum(axis=1)
    df = df.sort_values("week", ascending=True)

    max_perf, min_perf = df["performance_score"].max(), df["performance_score"].min()

    # Define tags for color-coding
    week_tree.tag_configure('best', background="#2e8b57")     # green
    week_tree.tag_configure('worst', background="#8b0000")    # red
    week_tree.tag_configure('neutral', background="#3b3b3b")  # gray

    # Insert each week's row with tags
    for _, row in df.iterrows():
        perf = row["performance_score"]
        if perf == max_perf:
            tag = 'best'
        elif perf == min_perf:
            tag = 'worst'
        else:
            tag = 'neutral'
        week_tree.insert('', END, values=list(row.drop("performance_score")), tags=(tag,))
        
    week_tree.pack(fill=BOTH, expand=True)
    
    # ====================================================================
    # === Defensive Team Stats (Pass + Run) ===
    # ====================================================================
    def_team = def_var.get()

    try:
        pass_df = pass_def(def_team)
        run_df = run_def(def_team)
    except Exception as e:
        messagebox.showerror("Error Loading Defense Data", f"Could not load defensive stats for {def_team}:\n{e}")
        return

    # PASS DEFENSE
    Label(scrollable_frame, text=f"{def_team} Pass Defense (Yards/Completions Allowed):",
          bg="#2b2b2b", fg="white", font=("Helvetica", 16, "italic")).pack(pady=(10, 5))
    frame_pass = Frame(scrollable_frame)
    frame_pass.pack(fill=BOTH, expand=True, padx=20, pady=10)

    pass_cols = list(pass_df.columns)
    pass_tree = ttk.Treeview(frame_pass, columns=pass_cols, show='headings', style="mystyle.Treeview")
    for col in pass_cols:
        pass_tree.heading(col, text=col)
        pass_tree.column(col, anchor=CENTER, width=110)
    # Insert week-by-week rows
    for _, row in pass_df.iterrows():
        pass_tree.insert('', END, values=list(row))

    # Compute averages and stds
    mean_row = pass_df.mean(numeric_only=True).to_dict()
    std_row = pass_df.std(numeric_only=True).to_dict()

    # Fill missing columns with blanks for safety
    mean_values = [round(mean_row.get(col, ""), 2) if isinstance(mean_row.get(col, ""), (int, float)) else "" for col in pass_cols]
    std_values = [round(std_row.get(col, ""), 2) if isinstance(std_row.get(col, ""), (int, float)) else "" for col in pass_cols]

    # Add summary rows (with tag styling)
    pass_tree.tag_configure('avg', background="#2e8b57", foreground="white")
    pass_tree.tag_configure('std', background="#555555", foreground="white")

    pass_tree.insert('', END, values=mean_values, tags=('avg',))
    pass_tree.insert('', END, values=std_values, tags=('std',))

    # Label the first cell of the summary rows
    pass_tree.set(pass_tree.get_children()[-2], pass_cols[0], "Average")
    pass_tree.set(pass_tree.get_children()[-1], pass_cols[0], "Std Dev")

    pass_tree.pack(fill=BOTH, expand=True)

    # RUN DEFENSE
    Label(scrollable_frame, text=f"{def_team} Run Defense (Yards/Attempts Allowed):",
          bg="#2b2b2b", fg="white", font=("Helvetica", 18, "italic")).pack(pady=(10, 5))
    frame_run = Frame(scrollable_frame)
    frame_run.pack(fill=BOTH, expand=True, padx=20, pady=10)

    run_cols = list(run_df.columns)
    run_tree = ttk.Treeview(frame_run, columns=run_cols, show='headings', style="mystyle.Treeview")
    for col in run_cols:
        run_tree.heading(col, text=col)
        run_tree.column(col, anchor=CENTER, width=110)
    for _, row in run_df.iterrows():
        run_tree.insert('', END, values=list(row))
    
    # Compute averages and stds
    mean_row = run_df.mean(numeric_only=True).to_dict()
    std_row = run_df.std(numeric_only=True).to_dict()

    mean_values = [round(mean_row.get(col, ""), 2) if isinstance(mean_row.get(col, ""), (int, float)) else "" for col in run_cols]
    std_values = [round(std_row.get(col, ""), 2) if isinstance(std_row.get(col, ""), (int, float)) else "" for col in run_cols]

    # Add summary rows (color coded)
    run_tree.tag_configure('avg', background="#2e8b57", foreground="white")
    run_tree.tag_configure('std', background="#555555", foreground="white")

    run_tree.insert('', END, values=mean_values, tags=('avg',))
    run_tree.insert('', END, values=std_values, tags=('std',))

    # Label the first cell
    run_tree.set(run_tree.get_children()[-2], run_cols[0], "Average")
    run_tree.set(run_tree.get_children()[-1], run_cols[0], "Std Dev")

    run_tree.pack(fill=BOTH, expand=True)

    canvas.update_idletasks()
    canvas.yview_moveto(0)

    # Add a close button
    Button(scrollable_frame, text="Close", command=result_window.destroy, bg="#444", fg="white").pack(pady=10)

# === Layout ===
Label(left_panel, text="Select Offense:", bg="#2b2b2b", fg="white").grid(row=0, column=0, padx=10, pady=10, sticky="e")
OptionMenu(left_panel, off_var, *teams).grid(row=0, column=1, padx=10, pady=10)

Label(left_panel, text="Select Defense:", bg="#2b2b2b", fg="white").grid(row=1, column=0, padx=10, pady=10, sticky="e")
OptionMenu(left_panel, def_var, *teams).grid(row=1, column=1, padx=10, pady=10)

Label(left_panel, text="Select Position:", bg="#2b2b2b", fg="white").grid(row=2, column=0, padx=10, pady=10, sticky="e")
pos_menu = OptionMenu(left_panel, pos_var, *(['select:'] + pos_groups))
pos_menu.grid(row=2, column=1, padx=10, pady=10)
pos_menu.config(state='disabled')

submit_btn = ttk.Button(left_panel, text="Submit", command=submit, state='disabled')
submit_btn.grid(row=4, column=0, columnspan=2, pady=20)

def swap_teams():
    if off_var.get() == 'select:' or def_var.get() == 'select:':
        return  # ignore swap if not valid
    
    # Temporarily disable trace callbacks while swapping
    if off_trace_id is not None:
        off_var.trace_remove("write", off_trace_id)
    if def_trace_id is not None:
        def_var.trace_remove("write", def_trace_id)

    current_off = off_var.get()
    current_def = def_var.get()

    off_var.set(current_def)
    def_var.set(current_off)

    # Re-enable validation callback
    attach_traces()

    # Re-run validation once AFTER swap is complete
    validate_selection()

# Swap Teams button
swap_btn = ttk.Button(left_panel, text="Swap Off/Def", command=swap_teams)
swap_btn.grid(row=5, column=0, columnspan=2, pady=(0,10))

# === Upcoming Schedule ===
Label(right_panel, text="Upcoming Games (Next 7 Days):", bg="#2b2b2b", fg="white",
      font=("Helvetica", 12, "bold")).pack(anchor="w")

games_list = Listbox(right_panel, height=12, width=30, bg="#1e1e1e", fg="white",
                     selectbackground="#3a86ff", activestyle="none")
games_list.pack(pady=10)

def populate_schedule():
    try:
        schedule = upcoming_schedule()
        schedule = schedule.sort_values("gameday")
        games_list.delete(0, END)

        for _, row in schedule.iterrows():
            date_str = pd.to_datetime(row['gameday']).strftime('%a %m/%d')
            away = row['away_team']
            home = row['home_team']
            display = f"{date_str}: {away} @ {home}"
            games_list.insert(END, display)
    except Exception as e:
        games_list.insert(END, f"Error loading schedule: {e}")

populate_schedule()

def on_game_select(event):
    selection = games_list.get(games_list.curselection())
    
    # Parse "Thu 10/31: BUF @ MIA"
    parts = selection.split(": ")[1]
    away, home = parts.split(" @ ")

    # Default selection: home = offense, away = defense
    off_var.set(home)
    def_var.set(away)

games_list.bind("<<ListboxSelect>>", on_game_select)

root.mainloop()


# In[ ]:




