import pygame
import math
import os
from settings import G, COLORS, SCREEN_WIDTH, SCREEN_HEIGHT, FPS
from engine import CelestialBody, Ship, Camera, load_universe, load_ship, init_ship_orbit, compute_gravity, \
    get_dominant_body, save_game, load_game

pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Orbital Mechanics 7.1 - Perfect Insertion & FX")
clock = pygame.time.Clock()
font = pygame.font.SysFont("Consolas", 14)
ui_font = pygame.font.SysFont("Consolas", 12)
title_font = pygame.font.SysFont("Consolas", 48, bold=True)


# ================= 渲染系统 =================
def draw_ship(screen, ship, camera, font):
    sx, sy = camera.apply(ship.x, ship.y)
    length, width = 12, 7
    cos_h, sin_h = math.cos(ship.heading), math.sin(ship.heading)
    nose = (sx + cos_h * length, sy + sin_h * length)
    left = (sx - cos_h * length + sin_h * width, sy - sin_h * length - cos_h * width)
    right = (sx - cos_h * length - sin_h * width, sy - sin_h * length + cos_h * width)

    # --- 优化1：主引擎火焰大幅加长 ---
    if ship.thrust_percent > 0:
        flame_len = length * 5.0 * ship.thrust_percent  # 从2.0提升到5.0
        flame_width = width * 0.4
        f_left = (sx - cos_h * length + sin_h * flame_width, sy - sin_h * length - cos_h * flame_width)
        f_right = (sx - cos_h * length - sin_h * flame_width, sy - sin_h * length + cos_h * flame_width)
        flame_tip = (sx - cos_h * (length + flame_len), sy - sin_h * (length + flame_len))
        pygame.draw.polygon(screen, COLORS["orange"], [f_left, f_right, flame_tip])

    if ship.turn_cmd != 0:
        rcs_color, rcs_len = COLORS["white"], 6
        if ship.turn_cmd < 0:
            pygame.draw.line(screen, rcs_color, nose, (nose[0] - sin_h * rcs_len, nose[1] + cos_h * rcs_len), 2)
            pygame.draw.line(screen, rcs_color, left, (left[0] + sin_h * rcs_len, left[1] - cos_h * rcs_len), 2)
        else:
            pygame.draw.line(screen, rcs_color, nose, (nose[0] + sin_h * rcs_len, nose[1] - cos_h * rcs_len), 2)
            pygame.draw.line(screen, rcs_color, right, (right[0] - sin_h * rcs_len, right[1] + cos_h * rcs_len), 2)

    pygame.draw.polygon(screen, ship.color, [nose, left, right])

    if ship.show_ui:
        panel_w, panel_h = 180, 75
        panel_x, panel_y = sx + 20, sy - panel_h // 2
        surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        surf.fill(COLORS["ui_bg"])
        screen.blit(surf, (panel_x, panel_y))
        pygame.draw.rect(screen, ship.color, (panel_x, panel_y, panel_w, panel_h), 1)

        lines = [
            f"Vessel: {ship.name}",
            f"Dest: {ship.autopilot_target.name if ship.autopilot_target else 'None'}",
            f"Phase: {ship.ap_state}",
            f"Thrust: {ship.thrust_percent * 100:.0f}%"
        ]
        for i, text in enumerate(lines):
            color = COLORS["orange"] if "ORBIT" in text or ship.thrust_percent > 0 else COLORS["white"]
            screen.blit(font.render(text, True, color), (panel_x + 5, panel_y + 5 + i * 16))


def draw_trajectory(screen, ship, bodies, camera):
    dom = get_dominant_body(ship.x, ship.y, bodies)
    if not dom: return
    rel_x, rel_y = ship.x - dom.x, ship.y - dom.y
    rel_vx, rel_vy = ship.vx - dom.get_velocity()[0], ship.vy - dom.get_velocity()[1]

    r, v = math.hypot(rel_x, rel_y), math.hypot(rel_vx, rel_vy)
    eps = v ** 2 / 2 - G * dom.mass / r

    if eps < 0:
        a = -G * dom.mass / (2 * eps)
        sim_dt, sim_steps = 2 * math.pi * math.sqrt(a ** 3 / (G * dom.mass)) / 200.0, 200
    else:
        sim_dt, sim_steps = max(10.0, r / max(v, 0.001) / 50.0), 200

    points = []
    for _ in range(sim_steps):
        dist_sq = rel_x ** 2 + rel_y ** 2
        if dist_sq < dom.body_radius ** 2:
            sx, sy = camera.apply(dom.x + rel_x, dom.y + rel_y)
            points.append((sx, sy));
            break

        dist = math.sqrt(dist_sq)
        f = -G * dom.mass / dist_sq
        rel_vx += f * (rel_x / dist) * sim_dt
        rel_vy += f * (rel_y / dist) * sim_dt
        rel_x += rel_vx * sim_dt
        rel_y += rel_vy * sim_dt

        sx, sy = camera.apply(dom.x + rel_x, dom.y + rel_y)
        if -500 < sx < SCREEN_WIDTH + 500 and -500 < sy < SCREEN_HEIGHT + 500:
            points.append((sx, sy))

    if len(points) > 1:
        pygame.draw.lines(screen, COLORS["cyan"], False, points, 1)


def draw_menus(screen, state, menu_options, selected_index):
    screen.fill(COLORS["menu_bg"])
    title_str = "ORBITAL MECHANICS" if state == "MAIN_MENU" else "PAUSED"
    t_surf = title_font.render(title_str, True, COLORS["white"])
    screen.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 200))

    for i, opt in enumerate(menu_options):
        color = COLORS["yellow"] if i == selected_index else COLORS["gray"]
        prefix = ">> " if i == selected_index else "   "
        opt_surf = title_font.render(prefix + opt, True, color)
        screen.blit(opt_surf, (SCREEN_WIDTH // 2 - 150, 350 + i * 60))


# ================= 主控制流 =================
def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    uni_path = os.path.join(base_dir, "Data", "Universe.xml")
    shp_path = os.path.join(base_dir, "Data", "Ships.xml")
    sav_path = os.path.join(base_dir, "Data", "savegame.json")

    game_state = "MAIN_MENU"
    menu_options = ["New Game", "Load Game", "Quit"]
    selected_idx = 0

    stars, all_bodies, ship, camera = None, None, None, None
    time_elapsed, time_scale, base_dt = 0.0, 1.0, 1.0
    view_targets, is_panning = [], False

    def setup_new_game():
        nonlocal stars, all_bodies, ship, camera, time_elapsed, time_scale, view_targets
        stars, all_bodies = load_universe(uni_path)
        ship = load_ship(shp_path)
        nearest = init_ship_orbit(ship, all_bodies)
        camera, camera.target = Camera(), nearest
        time_elapsed, time_scale = 0.0, 1.0
        view_targets = stars

    running = True
    while running:
        dt = base_dt * time_scale

        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False

            if game_state in ["MAIN_MENU", "PAUSED"]:
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_UP: selected_idx = (selected_idx - 1) % len(menu_options)
                    if event.key == pygame.K_DOWN: selected_idx = (selected_idx + 1) % len(menu_options)
                    if event.key == pygame.K_RETURN:
                        opt = menu_options[selected_idx]
                        if opt == "New Game":
                            setup_new_game();
                            game_state = "PLAYING"
                        elif opt == "Load Game":
                            setup_new_game()
                            loaded_time = load_game(sav_path, ship, camera, all_bodies)
                            if loaded_time is not None:
                                time_elapsed = loaded_time
                                game_state = "PLAYING"
                            else:
                                print("No Save File Found!")
                        elif opt == "Resume":
                            game_state = "PLAYING"
                        elif opt == "Save Game":
                            save_game(sav_path, time_elapsed, ship, camera); game_state = "PLAYING"
                        elif opt == "Quit to Menu":
                            game_state = "MAIN_MENU";
                            menu_options = ["New Game", "Load Game", "Quit"];
                            selected_idx = 0
                        elif opt == "Quit":
                            running = False

            elif game_state == "PLAYING":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    game_state = "PAUSED";
                    menu_options = ["Resume", "Save Game", "Quit to Menu"];
                    selected_idx = 0

                elif event.type == pygame.MOUSEWHEEL:
                    camera.scale *= 1.2 if event.y > 0 else 1 / 1.2
                    camera.scale = max(1e-10, min(camera.scale, 10.0))

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mx, my = event.pos
                        sx, sy = camera.apply(ship.x, ship.y)
                        # 点击飞船本身即可切换UI显示
                        if math.hypot(mx - sx, my - sy) <= 20:
                            ship.show_ui = not ship.show_ui
                        else:
                            for body in all_bodies:
                                bx, by = camera.apply(body.x, body.y)
                                render_r = max(int(body.render_size), int(body.body_radius * camera.scale))
                                if math.hypot(mx - bx, my - by) <= render_r + 15:
                                    camera.target = body;
                                    camera.reset_offset()
                                    break
                    elif event.button == 3:
                        is_panning = True

                elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
                    is_panning = False
                elif event.type == pygame.MOUSEMOTION and is_panning:
                    camera.offset_x -= event.rel[0] / camera.scale
                    camera.offset_y -= event.rel[1] / camera.scale

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RIGHTBRACKET:
                        time_scale = min(time_scale * 2.0, 1000000.0)
                    elif event.key == pygame.K_LEFTBRACKET:
                        time_scale = max(time_scale / 2.0, 1.0)
                    elif event.key == pygame.K_1:
                        camera.view_level = 0;
                        camera.target = None;
                        camera.reset_offset();
                        camera.scale = 1e-8
                    elif event.key == pygame.K_2:
                        camera.view_level = 1;
                        camera.target = stars[0];
                        camera.reset_offset();
                        camera.scale = 2e-6
                    elif event.key == pygame.K_4:
                        camera.view_level = 3;
                        camera.target = min(all_bodies, key=lambda b: math.hypot(ship.x - b.x, ship.y - b.y))
                        camera.reset_offset();
                        camera.scale = 0.002
                    elif event.key == pygame.K_RETURN and camera.target:
                        ship.autopilot_target = None if ship.autopilot_target == camera.target else camera.target

        if game_state != "PLAYING":
            draw_menus(screen, game_state, menu_options, selected_idx)
            pygame.display.flip()
            clock.tick(FPS)
            continue

        # ================= 飞控系统 =================
        keys = pygame.key.get_pressed()
        max_accel = ship.thrust / ship.mass
        ship.turn_cmd, ship.thrust_percent, accel_val = 0, 0.0, 0.0

        if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT] or keys[pygame.K_UP]:
            ship.autopilot_target, ship.ap_state = None, "MANUAL"
            if keys[pygame.K_LEFT]:  ship.heading -= 0.05; ship.turn_cmd = -1
            if keys[pygame.K_RIGHT]: ship.heading += 0.05; ship.turn_cmd = 1
            if keys[pygame.K_UP]:    ship.thrust_percent, accel_val = 1.0, max_accel

        elif ship.autopilot_target:
            target = ship.autopilot_target
            rel_x, rel_y = target.x - ship.x, target.y - ship.y
            dist = math.hypot(rel_x, rel_y)
            sync_dist = max(target.body_radius * 1.5, 100.0)

            ur_x, ur_y = rel_x / dist, rel_y / dist
            ut_x, ut_y = -ur_y, ur_x
            v_tan_mag = math.sqrt(G * target.mass / max(dist, 1.0))

            # 平滑径向靠近速度，防止震荡
            v_rad_desired = 0.05 * (dist - sync_dist)
            max_app_speed = math.sqrt(max(0, 2 * max_accel * abs(dist - sync_dist))) * 0.5
            v_rad_desired = max(-max_app_speed, min(max_app_speed, v_rad_desired))

            tvx, tvy = target.get_velocity()
            desired_vx, desired_vy = tvx + v_tan_mag * ut_x + v_rad_desired * ur_x, tvy + v_tan_mag * ut_y + v_rad_desired * ur_y
            dvx, dvy = desired_vx - ship.vx, desired_vy - ship.vy
            dv_mag = math.hypot(dvx, dvy)

            # --- 优化2：更强大的高倍速容差捕捉机制 ---
            # 速度误差放宽至 0.5 km/s，距离误差放宽至目标半径的 20%
            if dv_mag < 0.5 and abs(dist - sync_dist) < target.body_radius * 0.2:
                ship.ap_state = "STABLE ORBIT"
                ship.thrust_percent, ship.turn_cmd = 0.0, 0
                # 瞬间将其绝对锁定在完美圆形轨道上
                ship.x, ship.y = target.x - ur_x * sync_dist, target.y - ur_y * sync_dist
                ship.vx, ship.vy = tvx + v_tan_mag * ut_x, tvy + v_tan_mag * ut_y
                ship.heading = math.atan2(ship.vy - tvy, ship.vx - tvx)
            else:
                target_heading = math.atan2(dvy, dvx)
                angle_diff = (target_heading - ship.heading + math.pi) % (2 * math.pi) - math.pi

                # 如果时间加速开启（流速很快），允许飞船瞬间完成姿态调整，防止因错过窗口而卡住
                turn_speed = 0.1 if time_scale < 50 else math.pi

                if abs(angle_diff) > turn_speed:
                    ship.heading += turn_speed * (1 if angle_diff > 0 else -1)
                    ship.turn_cmd, ship.ap_state = 1 if angle_diff > 0 else -1, "ALIGNING"
                else:
                    ship.heading, ship.turn_cmd = target_heading, 0
                    if abs(angle_diff) < 0.2:
                        ship.ap_state = "TRANSFER BURN" if dist > sync_dist * 2 else "ORBIT INSERTION"
                        actual_accel = min(max_accel, dv_mag * 0.5, dv_mag / max(dt, 0.001))
                        ship.thrust_percent, accel_val = actual_accel / max_accel, actual_accel

        thrust_x, thrust_y = math.cos(ship.heading) * accel_val, math.sin(ship.heading) * accel_val

        # ================= 物理引擎更新 =================
        time_elapsed += dt
        for star in stars: star.set_time(time_elapsed)

        if dt > 0:
            physics_steps = max(1, int(dt / 3600))
            sim_dt = dt / physics_steps
            for _ in range(physics_steps):
                ax, ay = compute_gravity(ship.x, ship.y, all_bodies)
                ship.vx += (ax + thrust_x) * sim_dt
                ship.vy += (ay + thrust_y) * sim_dt
                ship.x += ship.vx * sim_dt
                ship.y += ship.vy * sim_dt

        # ================= 渲染画面 =================
        screen.fill((5, 5, 15))

        for body in all_bodies:
            if body.parent:
                cx, cy = camera.apply(body.parent.x, body.parent.y)
                radius = int(body.orbit_radius * camera.scale)
                if 2 < radius < 8000: pygame.draw.circle(screen, COLORS["dark_gray"], (cx, cy), radius, 1)

        draw_trajectory(screen, ship, all_bodies, camera)

        for body in all_bodies:
            sx, sy = camera.apply(body.x, body.y)
            render_r = max(int(body.render_size), int(body.body_radius * camera.scale))
            if body == camera.target: pygame.draw.circle(screen, COLORS["green"], (sx, sy), render_r + 4, 1)
            pygame.draw.circle(screen, body.color, (sx, sy), render_r)
            if camera.scale > 1e-6: screen.blit(font.render(body.name, True, COLORS["white"]),
                                                (sx + render_r + 5, sy - 10))

        draw_ship(screen, ship, camera, ui_font)

        ui_texts = [
            f"Mode: {['1: Uni', '2: Sol', '3: Sys', '4: Tgt'][camera.view_level]} (ESC for Menu)",
            f"Target: {camera.target.name if camera.target else 'ALL'} (L-Click)",
            f"Time Scale: {time_scale}x (Keys [ and ])",
            f"Spd: {math.hypot(ship.vx, ship.vy):.2f} km/s"
        ]
        for i, text in enumerate(ui_texts):
            screen.blit(font.render(text, True, COLORS["green"]), (10, 10 + i * 22))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()