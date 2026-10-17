// SQ-2 high-speed quad, parametric outer mould line.
// Default numbers are the v3 optimiser output: speed-quad/cad/out/sq2/params.json.
// x = body axis (nose at 0), mm. Edit any parameter or any module; FORGE recompiles in-browser.

stage = 9;              // [0:9] build stage shown (replay)

// Fuselage
body_length = 547;      // [300:800] overall length
body_diameter = 100.3;  // [60:160] max diameter
nose_length = 135;      // [40:300] nose cone length
nose_shape = 0.5;       // [0.05:1] power-law exponent: 1 = sharp straight cone, 0.7 = pointed ogive, 0.5 = ogive, 0.2 = blunt bullet
tail_length = 126;      // [40:300] boat-tail length
tail_end_d = 26;        // [0:80] boat-tail exit diameter

// Arms (struts)
arm_count = 4;          // [2:8]
arm_clock = 45;         // [0:90] first arm angle from dorsal, deg
arm_station = 400;      // [150:600] strut quarter-chord station
pod_radius = 160;       // [90:300] body axis to pod axis
strut_chord = 57;       // [20:120]
strut_tc = 0.155;       // [0.06:0.3] thickness / chord
strut_camber = 0;       // [0:0.08] NACA 4-digit max camber
strut_camber_pos = 0.4; // [0.2:0.7]
strut_sweep = 0;        // [-30:45] deg
strut_taper = 1.0;      // [0.4:1.2] tip chord / root chord

// Pods (motor nacelles)
pod_diameter = 41.2;    // [25:70]
pod_length = 181;       // [80:300]
pod_offset = -72;       // [-150:50] pod front relative to strut station
pod_nose_shape = 0.5;   // [0.05:1] 1 = sharp cone, 0.2 = blunt
pod_nose_length = 40;   // [10:120]
pod_tail_length = 60;   // [10:150]
pod_tail_end_d = 8;     // [0:30]

// Props
prop_diameter = 165;    // [80:260]
blade_count = 2;        // [2:5]
blade_chord = 16;       // [6:40]
blade_pitch = 22;       // [0:45] deg

// Tail fins
fin_count = 4;          // [0:6]
fin_clock = 45;         // [0:90]
fin_span = 70.5;        // [0:150]
fin_root = 45.3;        // [15:120]
fin_taper = 0.5;        // [0.2:1]
fin_sweep = 35;         // [0:60]
fin_tc = 0.12;          // [0.05:0.2]

body_color = [0.17, 0.17, 0.19];
pod_color = [0.21, 0.21, 0.23];
spinner_color = [0.92, 0.22, 0.2];
strut_color = [0.42, 0.43, 0.46];
prop_color = [0.08, 0.08, 0.09];
fin_color = [0.42, 0.43, 0.46];
dome_color = [0.85, 0.86, 0.82];

$fn = 48;
N = 40;   // profile stations

// ---------- shape functions ----------
function nose_r(x, ln, R, n) = R * pow(max(x, 0) / ln, n);
function tail_r(s, R, re) = R + (re - R) * (3*s*s - 2*s*s*s);
function body_r(x) =
    x <= nose_length ? nose_r(x, nose_length, body_diameter/2, nose_shape) :
    x <= body_length - tail_length ? body_diameter/2 :
    tail_r((x - (body_length - tail_length)) / tail_length, body_diameter/2, tail_end_d/2);
function pod_r(x) =
    x <= pod_nose_length ? nose_r(x, pod_nose_length, pod_diameter/2, pod_nose_shape) :
    x <= pod_length - pod_tail_length ? pod_diameter/2 :
    tail_r((x - (pod_length - pod_tail_length)) / pod_tail_length, pod_diameter/2, pod_tail_end_d/2);

// revolve r(x) profile about +x
module revolve_x(pts) {
    rotate([0, 90, 0])
        rotate_extrude($fn = 64) polygon(concat([[0, pts[0][1]]], pts, [[0, pts[len(pts)-1][1]]]));
}
function body_pts() = [for (i = [0:N]) let(x = body_length * (1 - cos(i * 180 / N)) / 2) [max(body_r(x), 0.01), x]];
function pod_pts() = [for (i = [0:N]) let(x = pod_length * (1 - cos(i * 180 / N)) / 2) [max(pod_r(x), 0.01), x]];

// NACA 4-digit section, chord along +x, thickness along y, closed trailing edge
function naca_yt(xc, t) = 5 * t * (0.2969*sqrt(xc) - 0.1260*xc - 0.3516*xc*xc + 0.2843*pow(xc,3) - 0.1036*pow(xc,4));
function naca_yc(xc, m, p) = m == 0 ? 0 :
    xc < p ? m / (p*p) * (2*p*xc - xc*xc) : m / ((1-p)*(1-p)) * ((1 - 2*p) + 2*p*xc - xc*xc);
function naca(c, t, m = 0, p = 0.4, n = 24) =
    let(xs = [for (i = [0:n]) (1 - cos(i * 180 / n)) / 2])
    concat([for (i = [0:n]) [c*xs[i], c*(naca_yc(xs[i], m, p) + naca_yt(xs[i], t))]],
           [for (i = [n-1:-1:1]) [c*xs[i], c*(naca_yc(xs[i], m, p) - naca_yt(xs[i], t))]]);

// tapered, swept wing panel growing along +z from z=0
module panel(chord, tc, span, taper, sweep, m = 0, p = 0.4) {
    multmatrix([[1, 0, tan(sweep), 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        linear_extrude(height = span, scale = taper)
            translate([-chord/4, 0]) polygon(naca(chord, tc, m, p));
}

// ---------- components ----------
module fuselage() {
    color(body_color) revolve_x(body_pts());
    color(dome_color) translate([max(nose_length * 0.06, 2), 0, 0]) sphere(d = max(body_r(nose_length*0.12)*1.6, 4), $fn = 24);
}

module strut(a) {
    r0 = body_diameter / 2 * 0.85;
    rotate([a, 0, 0]) translate([arm_station, 0, r0])
        color(strut_color) panel(strut_chord, strut_tc, pod_radius - r0, strut_taper, strut_sweep, strut_camber, strut_camber_pos);
}

function strut_tip_x() = arm_station + tan(strut_sweep) * (pod_radius - body_diameter/2*0.85);

module pod(a) {
    rotate([a, 0, 0]) translate([strut_tip_x() + pod_offset, 0, pod_radius])
        color(pod_color) revolve_x(pod_pts());
}

module prop(a) {
    rotate([a, 0, 0]) translate([strut_tip_x() + pod_offset - 6, 0, pod_radius]) {
        color(spinner_color) rotate([0, 90, 0]) cylinder(h = 14, r1 = 0.5, r2 = pod_diameter * 0.42, $fn = 32);
        color(prop_color) for (b = [0 : blade_count - 1]) rotate([b * 360 / blade_count, 0, 0])
            linear_extrude(height = prop_diameter / 2, scale = 0.45, twist = -blade_pitch)
                rotate([0, 0, blade_pitch]) scale([1.6, blade_chord / 2]) circle(r = 1, $fn = 16);
    }
}

module fins() {
    x0 = body_length - fin_root - 4;
    r0 = body_r(x0 + fin_root * 0.5) * 0.9;
    if (fin_count > 0) for (i = [0 : fin_count - 1]) rotate([fin_clock + i * 360 / fin_count, 0, 0])
        translate([x0 + fin_root / 4, 0, r0]) color(fin_color) panel(fin_root, fin_tc, fin_span, fin_taper, fin_sweep);
}

module sq2() {
    if (stage >= 1) fuselage();
    if (stage >= 2) for (i = [0 : arm_count - 1]) strut(arm_clock + i * 360 / arm_count);
    if (stage >= 3) for (i = [0 : arm_count - 1]) pod(arm_clock + i * 360 / arm_count);
    if (stage >= 4) for (i = [0 : arm_count - 1]) prop(arm_clock + i * 360 / arm_count);
    if (stage >= 5) fins();
}

sq2();
