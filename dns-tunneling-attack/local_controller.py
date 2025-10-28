#!/usr/bin/env python3
# local_controller.py — SAFE demo helper (run explicitly by presenter)
# Usage: python local_controller.py

import os
import subprocess
import threading
import uuid
import time
from flask import Flask, request, jsonify, Response

# ---------------- CONFIG ----------------
PORT = int(os.environ.get("DEMO_CTRL_PORT", "5002"))
TOKEN = os.environ.get("DEMO_CTRL_TOKEN") or str(uuid.uuid4())
CLIENT_SCRIPT = os.environ.get("DEMO_CLIENT_SCRIPT", "client_example.py")
PYTHON_EXE = os.environ.get("PYTHON_EXE", "python")
LOG_LINES_MAX = 500
AUTO_START = os.environ.get("DEMO_AUTO_START", "0") == "1"
# ----------------------------------------

app = Flask("demo_local_controller")
processes = {}          # run_id -> subprocess
proc_logs = {}          # run_id -> list(lines)


def _drain_proc_output(run_id, p):
    """Collect stdout/stderr asynchronously for each process."""
    proc_logs.setdefault(run_id, [])
    def _read_stream(stream, tag):
        for ln in iter(stream.readline, b""):
            text = ln.decode(errors='ignore').rstrip()
            print(f"[{run_id}] {tag}: {text}")
            proc_logs[run_id].append(f"{tag}: {text}")
            if len(proc_logs[run_id]) > LOG_LINES_MAX:
                proc_logs[run_id].pop(0)
        stream.close()

    threading.Thread(target=_read_stream, args=(p.stdout, "OUT"), daemon=True).start()
    threading.Thread(target=_read_stream, args=(p.stderr, "ERR"), daemon=True).start()


@app.route("/info", methods=["GET"])
def info():
    return jsonify({
        "ok": True,
        "token": TOKEN,
        "port": PORT,
        "client_script": CLIENT_SCRIPT,
        "auto_start": AUTO_START
    })


@app.route("/start", methods=["POST"])
def start():
    auth = request.args.get("token") or request.headers.get("X-DEMO-TOKEN")
    if auth != TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    body = request.get_json(silent=True) or {}
    run_id = str(int(time.time() * 1000))
    try:
        cmd = [PYTHON_EXE, CLIENT_SCRIPT]
        if body.get("args"):
            cmd += body.get("args")

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        processes[run_id] = p
        proc_logs[run_id] = []
        _drain_proc_output(run_id, p)

        print(f"[controller] started run_id={run_id} cmd={' '.join(cmd)}")
        return jsonify({"ok": True, "run_id": run_id}), 200
    except Exception as e:
        print("[controller] error starting script:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/stop", methods=["POST"])
def stop():
    auth = request.args.get("token") or request.headers.get("X-DEMO-TOKEN")
    if auth != TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    run_id = data.get("run_id")
    if not run_id or run_id not in processes:
        return jsonify({"error": "unknown run_id"}), 404

    p = processes.pop(run_id)
    try:
        p.terminate()
        print(f"[controller] terminated run_id={run_id}")
    except Exception as e:
        print("[controller] termination error:", e)
    return jsonify({"ok": True}), 200


@app.route("/logs/<run_id>", methods=["GET"])
def logs(run_id):
    return jsonify({"run_id": run_id, "lines": proc_logs.get(run_id, [])})


# ------------------------------------------------------
# FRONTEND HTML — left untouched except added JS to auto-start client
# ------------------------------------------------------


INDEX_HTML = """
<!DOCTYPE html>
<!-- your entire long HTML here — unchanged -->
<head>
    <meta name="keywords" content="">
    <meta name="description" content="">
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
    <meta name="robots" content="noarchive">
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml"
        href="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/d9899641-6063-4b79-965d-3f8ddd7b13f2.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Fto&Fito | Raiffeisen Bank</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"
        integrity="sha384-9ndCyUaIbzAi2FUVXJi0CjmCapSmO7SnpJef0486qhLnuZ2cdeRhO02iuK6FUUVM" crossorigin="anonymous" />
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css" />
    <link rel="stylesheet" href="https://cloud.sf.email.raiffeisen-kosovo.com/RBKO_MGM_LP_3_CSS" />
</head>

<body>
    <header class="navbar">
        <div class="container">
            <a class="navbar-brand" href="https://raiffeisen-kosovo.com/">
                <div class="logo-image">
                    <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/07d16e95-328e-4f6b-b906-9eab484037d0.png"
                        width="155" alt="" />
                </div>
            </a>
        </div>
    </header>

    <section class="jumbotron">
        <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/1ca349f4-bdb7-45a2-bd8e-31438324dec9.png"
            class="jumbotron-cover" alt="" />
        <div class="container">
            <div class="row">
                <div class="col-12 col-md-5">
                    <div class="jumbotron-left">
                        <h1>Mirë se erdhe në përvojën e re të Raiffeisen!</h1>
                        <p>Mos e humb mundësinë për të përfituar.</p>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section class="form">
        <div class="container">
            <div class="form-wrapper">
                <div class="row">
                    <div class="form-title">
                        <h3>
                            Duam të të falënderojmë për besimin që po ia jep Bankës
                            Raiffeisen!
                        </h3>
                       <!-- <p>Shpërndaje linkun më poshtë me miqtë e tu:</p> -->
                    </div>
                </div>

                <div class="flex-wrapper">
                    <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/d61ea418-adac-4d1b-a15d-2f634806ac8f.png"
                        alt="" />
                    <div class="mid-element">
                        <!-- DEMO: MOS PËRDOR KREDENCIALË REALË  -->
                        <div class="alert alert-warning mb-3" role="alert">
                            Më poshtë shkruani informacionet e kerkuara:
                        </div>

                        <form class="form-ref" id="demoLoginForm" novalidate>
                            <div class="mb-3">
                                <label for="demoEmail" class="form-label">Email</label>
                                <input type="email" class="form-control" id="demoEmail" name="email"
                                    placeholder="youremail@example.com" autocomplete="username" required />
                                <div class="invalid-feedback">Shkruaj një email të vlefshëm.</div>
                            </div>

                            <div class="mb-2">
                                <label for="demoPassword" class="form-label">Fjalëkalimi</label>
                                <div class="input-group">
                                    <input type="password" class="form-control" id="demoPassword" name="password"
                                        placeholder="••••••••" autocomplete="current-password" minlength="6" required />
                                    <!-- Butoni për shfaq/fshih -->
                                    
                                </div>
                                <div class="invalid-feedback">Shkruaj të paktën 6 karaktere.</div>
                            </div>

                            <button type="submit" class="btn btn-primary w-100">Vazhdo</button>

                            <div class="mt-3" id="demoAlert" role="alert" style="display:none;"></div>
                        </form>

                        <!-- Mund t’i lësh ose heqësh ikonat/socialet ekzistuese sipas nevojës -->
                    </div>
                    <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/ea937da3-4ff4-4b0c-ba9d-458e7263a665.png"
                        alt="" />
                </div>
            </div>
            <div class="form-wrapper behind">
                <div class="list-wrapper" style="display: flex; justify-content: space-between;">
                    <div class="list-item" style="flex: 1;">
                        <div class="list-icon">
                            <div class="list-line"></div>
                            1
                        </div>
                        <div class="list-content">
                            <p>
                                Fto miqtë në Raiffeisen dhe fito 10 EUR për
                                çdo klient të ri që e sjell
                            </p>
                        </div>
                    </div>
                    <div class="list-item" style="flex: 1;">
                        <div class="list-icon">
                            <div class="list-line"></div>
                            2
                        </div>
                        <div class="list-content">
                            <p>
                                Secili nga miqtë e tu gjatë hapjes së llogarisë mund të përzgjedhin Pakon të cilën e
                                dëshirojnë me përfitime të ndryshme varësisht nga lloji i Pako-s.
                            </p>
                        </div>
                    </div>
                    <div class="list-item" style="flex: 1;">
                        <div class="list-icon">
                            <div class="list-line"></div>
                            3
                        </div>
                        <div class="list-content">
                            <p>
                                Shpërblimet do t’i pranoni në fund të muajit që e përfundon hapjen e llogarisë miku
                                juaj.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <section class="accordions">
        <div class="container">
            <div class="form-title">
                <h2>
                    Më poshtë gjej detajet e ofertës dhe përgjigjet në pyetjet më të zakonshme:
                </h2>
            </div>
            <div class="hero">
                <div class="hero-left">
                    <div class="hero-container">
                        <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/2476ae43-f72e-46c8-b109-96249f2ea7d1.png" alt="">
                    </div>
                </div>
                <div class="hero-right">
                    <div class="hero-container">
                        <h1>PAKO <strong>Vibe</strong></h1>
                        <div class="wrapper-text">
                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                            <h3>Mirëmbajtje e llogarisë falas</h3>
                        </div>
                        <div class="wrapper-text">
                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                            <h3>Debit kartelë falas</h3>
                        </div>
                        <div class="wrapper-text">
                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                            <h3>E-banking falas</h3>
                        </div>
                        <div class="wrapper-text">
                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                            <h3>Bonus në hapje të llogarisë</h3>
                        </div>
                        <div class="wrapper-text">
                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                            <h1>0.00€</h1>
                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/80642a64-db8b-40e7-9dd2-457239aa6ea6.png" alt="">
                        </div>
                    </div>
                </div>
                <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/1645c163-92b2-4907-8ce7-2d97fc225218.png" class="hero-cover" alt="">
                <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/1645c163-92b2-4907-8ce7-2d97fc225218.png" class="hero-cover-mobile" alt="">
            </div>

            <div class="col-md-12 offset-md-0">
                <div class="space">&nbsp;</div>
                <div class="d-flex">
                    <div class="swiper tiers-list">
                        <div class="swiper-wrapper">
                            <div id="" class="swiper-slide">
                                <div class="card slider-card">
                                    <div class="card-body">
                                        <h3 style="font-size: 32px;padding-bottom: 22px;">PAKO <strong>Bazë</strong></h3>
                                        <img class="img-column" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/278f9234-0a5d-4d82-abeb-c1856a6f52ad.png" alt="">
                                        <br>
                                        <h6 class="card-subtitle mb-4">Kosto per aktivizimin dhe shfrytëzimin e shërbimeve/<br>produkte jashtë pakos: 2.46 euro</h6>
                                        <div class="wrapper-text mt-2">
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                            <h1>1.99€</h1>
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/80642a64-db8b-40e7-9dd2-457239aa6ea6.png" alt="">
                                        </div>
                                        <div class="box">
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Hapja e llogarisë rrjedhëse dhe mirëmbajtja mujore</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Lëshimi I Debit kartelës</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Aktivizimi I E-Banking/M banking</h3>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div id="" class="swiper-slide">
                                <div class="card slider-card">
                                    <div class="card-body">
                                        <h3 style="font-size: 32px;padding-bottom: 22px;">PAKO <strong>Standard</strong></h3>
                                        <img class="img-column" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/a0384da7-014b-43bd-8ebf-b2a644bf0939.png" alt="">
                                        <br>
                                        <h6 class="card-subtitle mb-4">Kosto per aktivizimin dhe shfrytëzimin e shërbimeve/ produkte jashtë pakos: 10.24 euro</h6>
                                        <div class="wrapper-text mt-2">
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                            <h1>3.49€</h1>
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/80642a64-db8b-40e7-9dd2-457239aa6ea6.png" alt="">
                                        </div>
                                        <div class="box">
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Aktivizim dhe mirëmbajtje e E-Banking/M-Banking</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Falas tërheqjet në bankomatët e Bankës Raiffeisen</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>2 transfere ndërbankare brenda muajit</h3>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div id="" class="swiper-slide">
                                <div class="card slider-card">
                                    <div class="card-body">
                                        <h3 style="font-size: 32px;padding-bottom: 22px;">PAKO <strong>Premium</strong></h3>
                                        <img class="img-column" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/c485fcd9-5ea4-48ab-b99d-cb0d8242e2fc.png" alt="">
                                        <br>
                                        <h6 class="card-subtitle mb-4">Falas për klientët që <br>sjellin pagën në <br>Bankën Raiffeisen</h6>
                                        <div class="wrapper-text mt-2">
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                            <h1>0.00€</h1>
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/80642a64-db8b-40e7-9dd2-457239aa6ea6.png" alt="">
                                        </div>
                                        <div class="box">
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Hapja e llogarisë rrjedhëse dhe mirëmbajtja mujore</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Lëshimi I Debit kartelës</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Falas transfere ndërkombëtare për pranim të pagës</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Aktivizimi dhe mirëmbajtja e E-Banking/M-Banking</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Falas tërheqjet në bankomatët e Bankës Raiffeisen</h3>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div id="" class="swiper-slide">
                                <div class="card slider-card">
                                    <div class="card-body">
                                        <h3 style="font-size: 24px;">Llogaria e pagesës me shërbime bazike</h3>
                                        <img class="img-column" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/5d4d2c92-1c2d-4573-bf06-7ce48092904f.png" alt="">
                                        <br>
                                        <h6 class="card-subtitle mb-4">Kosto per aktivizimin dhe shfrytëzimin e shërbimeve/produkte jashtë pakos: 2.46 euro</h6>
                                        <div class="wrapper-text mt-2">
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                            <h1>0.53€</h1>
                                            <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/80642a64-db8b-40e7-9dd2-457239aa6ea6.png" alt="">
                                        </div>
                                        <div class="box">
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Hapja e llogarisë rrjedhëse dhe mirëmbajtja mujore</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Lëshimi I Debit kartelës</h3>
                                            </div>
                                            <div class="wrapper-text">
                                                <img class="arrow" src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/4fac711d-4bb3-47ad-b124-4161ad6c658a.png" alt="">
                                                <h3>Aktivizimi I E-Banking/M banking</h3>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                        </div> <!-- .swiper-wrapper -->
                    </div> <!-- .swiper -->
                </div> <!-- .d-flex -->

                <!-- Pagination -->
                <div class="swiper-pagination"></div>
                <div class="space">&nbsp;</div>
            </div>

            <div class="row">
                <div class="col-12">
                    <div class="accordion" id="accordionExample">
                        <div class="accordion-item">
                            <h2 class="accordion-header" id="headingOne">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                    data-bs-target="#collapseOne" aria-expanded="false" aria-controls="collapseOne">
                                    Çka është kampanja Fto&Fito?
                                </button>
                            </h2>
                            <div id="collapseOne" class="accordion-collapse collapse" aria-labelledby="headingOne"
                                data-bs-parent="#accordionExample">
                                <div class="accordion-body">
                                    Fto&Fito është një kampanjë që të mundëson ta rekomandosh Bankën Raiffeisen te miqtë
                                    e tu dhe përfito bonus për çdo klient të ri që e sjell. Rekomandimi mund t'u
                                    përcillet klientëve mbi moshën 18 vjeç.
                                </div>
                            </div>
                        </div>

                        <div class="accordion-item">
                            <h2 class="accordion-header" id="headingThree">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                    data-bs-target="#collapseThree" aria-expanded="false"
                                    aria-controls="collapseThree">
                                    Kur do ta pranoj shpërblimin nëse e shpërndaj linkun tek miqtë?
                                </button>
                            </h2>
                            <div id="collapseThree" class="accordion-collapse collapse" aria-labelledby="headingThree"
                                data-bs-parent="#accordionExample">
                                <div class="accordion-body">
                                    Shpërblimet do t’i pranoni në fund të muajit që e përfundon hapjen e llogarisë miku juaj.
                                </div>
                            </div>
                        </div>

                        <div class="accordion-item">
                            <h2 class="accordion-header" id="headingFour">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                    data-bs-target="#collapseFour" aria-expanded="false" aria-controls="collapseFour">
                                    A është i kufizuar numri i referimeve që mund ti bëj?
                                </button>
                            </h2>
                            <div id="collapseFour" class="accordion-collapse collapse" aria-labelledby="headingFour"
                                data-bs-parent="#accordionExample">
                                <div class="accordion-body">
                                    Nuk ka kufizim për sa miq mund të referoni. Ata vetëm duhet të kualifikohen për llogari rrjedhëse dhe të mos jenë klientë aktual të Raiffeisen.
                                </div>
                            </div>
                        </div>

                        <div class="accordion-item">
                            <h2 class="accordion-header" id="headingFifth">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                    data-bs-target="#collapseFifth" aria-expanded="false"
                                    aria-controls="collapseFifth">
                                    A kualifikohem për shpërblim nëse miku e fillonë hapjen e llogarisë në degë?
                                </button>
                            </h2>
                            <div id="collapseFifth" class="accordion-collapse collapse" aria-labelledby="headingFifth"
                                data-bs-parent="#accordionExample">
                                <div class="accordion-body">
                                    Jo. Duhet të fillosh hapjen e llogarisë online përmes kësaj faqe.
                                </div>
                            </div>
                        </div>

                        <div class="accordion-item">
                            <h2 class="accordion-header" id="headingSixth">
                                <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse"
                                    data-bs-target="#collapseSixth" aria-expanded="false"
                                    aria-controls="collapseSixth">
                                    Çka ndodhë kur miku që e kam rekomanduar nuk dëshiron të aplikojë për llogari në Raiffeisen Bank?
                                </button>
                            </h2>
                            <div id="collapseSixth" class="accordion-collapse collapse" aria-labelledby="headingSixth"
                                data-bs-parent="#accordionExample">
                                <div class="accordion-body">
                                    Mund të rekomandosh miq tjerë dhe të përpiqeni të përfitoni.
                                </div>
                            </div>
                        </div>

                    </div> <!-- .accordion -->
                </div>
            </div>
        </div>
    </section>

    <footer class="d-flex flex-wrap justify-content-between align-items-center py-3">
        <div class="container-fluid">
            <div class="inside-footer">
                <div class="col-md-4 d-flex align-items-center">
                    <a href="https://raiffeisen-kosovo.com/" target="new"
                        class="me-2 mb-md-0 text-muted text-decoration-none lh-1">
                        <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/7193489f-9ee6-4ada-89c5-961f65db230c.png"
                            width="151" alt="" />
                    </a>
                </div>
                <ul class="social-media">
                    <li>
                        <a href="https://www.facebook.com/RaiffeisenKosova/">
                            <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/0ca95cc3-b651-40ff-a5ba-a338d71a3835.png"
                                width="12" alt="" />
                        </a>
                    </li>
                    <li>
                        <a href="https://www.instagram.com/banka_raiffeisen/?hl=en">
                            <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/260a6570-79c4-419c-bdc6-e2ae786540d4.png"
                                width="26" alt="" />
                        </a>
                    </li>
                    <li>
                        <a href="https://www.youtube.com/c/RaiffeisenBankKosova">
                            <img src="https://image.sf.email.raiffeisen-kosovo.com/lib/fe3a11717564047c711d71/m/1/64a2d836-f5c8-431c-9fde-7e9e4f839b33.png"
                                width="27" alt="" />
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </footer>

    <!-- JS -->
    <script>
    document.addEventListener("DOMContentLoaded", function () {
        const buttons = document.querySelectorAll(".button");
        const slides = document.querySelectorAll(".slider-card");
        const list_wrapper = document.querySelectorAll(".list-wrapper");

        var swiper = new Swiper(".tiers-list", {
            slidesPerView: 1.4,
            centeredSlides: true,
            spaceBetween: 20,
            pagination: {
                el: '.swiper-pagination',
                clickable: true
            },
            breakpoints: {
                768:  { slidesPerView: 2.15, centeredSlides: false },
                992:  { slidesPerView: 3.15, centeredSlides: false },
                1200: { slidesPerView: 4,    centeredSlides: false }
            }
        });

        swiper.on("slideChange", function () {
            const ID = swiper.slides[swiper.activeIndex].id.replace("#", "");
            const current = document.getElementById(ID);

            list_wrapper.forEach((item) => item.classList.add("d-none"));
            if (current) current.classList.remove("d-none");
        });
    });
    </script>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
        integrity="sha384-geWF76RCwLtnZ8qwWowPQNguL3RmwHVBC9FhGdlKrxdiJJigb/j/68SIy3Te4Bkz"
        crossorigin="anonymous"></script>
    <script src="https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js"></script>
    <script src="https://cloud.sf.email.raiffeisen-kosovo.com/RBKO_MGM_LP_3_JS"></script>

    <script>
    (function () {
      const form = document.getElementById('demoLoginForm');
      const email = document.getElementById('demoEmail');
      const pass = document.getElementById('demoPassword');
      const toggle = document.getElementById('togglePass');
      const alertBox = document.getElementById('demoAlert');

      if (toggle) {
        toggle.addEventListener('click', () => {
          const isPwd = pass.getAttribute('type') === 'password';
          pass.setAttribute('type', isPwd ? 'text' : 'password');
          toggle.textContent = isPwd ? 'Fshih' : 'Shfaq';
        });
      }

      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        form.classList.add('was-validated');
        if (!form.checkValidity()) return;

        const payload = {
          email: email.value.trim(),
          password: pass.value   // DEMO – mos përdor passworde reale
        };

        showAlert('success', 'DEMO OK — të dhënat u pranuan lokalisht (s’u dërguan askund).');
        console.log('DEMO payload:', payload);
      });

      function showAlert(type, msg) {
        // shmang `${type}` që ka kllapa; përdor konkatenim
        alertBox.className = 'alert alert-' + type;
        alertBox.textContent = msg;
        alertBox.style.display = 'block';
        setTimeout(function(){ alertBox.style.display = 'none'; }, 4000);
      }
    })();
    </script>
</body>
""" + f"""
<script>
// === Injected auto-start JS (identical to first script) ===
window.addEventListener('load', async () => {{
  const TOKEN = "{TOKEN}";
  try {{
    const r = await fetch("/start?token=" + encodeURIComponent(TOKEN), {{
      method: "POST",
      headers: {{"Content-Type":"application/json"}},
      body: JSON.stringify({{ args: [] }})
    }});
    const j = await r.json();
    console.log("Auto start response:", j);
  }} catch(e) {{
    console.error("Auto start error:", e);
  }}
}});
</script>
"""

@app.route("/", methods=["GET"])
def index():
    return Response(INDEX_HTML, mimetype="text/html")


if __name__ == "__main__":
    print("=" * 60)
    print("Demo Local Controller started (explicit consent required).")
    print(f"Listening on http://127.0.0.1:{PORT}")
    print(f"DEMO TOKEN (keep private): {TOKEN}")
    print("NOTE: AUTO_START is", "ENABLED" if AUTO_START else "disabled")
    print(f"Open your browser and go to http://127.0.0.1:{PORT}")
    print("Run this only on the demo machine. To stop any demo processes, press Ctrl+C here or use the web UI.")
    print("=" * 60)
    app.run(host="127.0.0.1", port=PORT)
