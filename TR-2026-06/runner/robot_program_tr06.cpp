// TR-2026-06 runner: initial-guess strategies C0..C3/C2z x checks V/T/V_cfg on 12 models x 60 linear moves,
// plus E1 (joint-speed rounding) and pre-checks. Output follows TR-06_결과형식_v1.md exactly; the product
// planner, IK and checker are called unchanged. See TR-2026-06 pre-registration v0.2 sections 3, 5, 6, 8, 9.
#include "robot_program_check.hpp"
#include "robot_program_planner.hpp"
#include <QCryptographicHash>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QStringList>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <functional>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
using namespace vexplor;
using program::Vector;

constexpr const char* expectedInputsSha = "43da27bf7d0e63d51fedc9341e5555206550f62f73d723f53c832606e0874f8a";
constexpr double tolJoint = .01, tolPos = .01, tolRot = .01, speedMargin = 1+1e-9;
constexpr double wristBandSin = 0.017452406437283512;  // sin(1 deg)
const ProgramJoints readyPose{0,-35,55,0,35,0};

QJsonArray six(const ProgramJoints& q) { QJsonArray a; for (double v : q) a.append(v); return a; }
ProgramJoints joints(const QJsonValue& v) {
  const auto a = v.toArray(); if (a.size() != 6) throw std::runtime_error("six joint values expected");
  ProgramJoints q{}; for (int i = 0; i < 6; ++i) q[static_cast<std::size_t>(i)] = a[i].toDouble(); return q;
}
QString utcNow() { return QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs); }
QByteArray sha256(const QByteArray& b) { return QCryptographicHash::hash(b,QCryptographicHash::Sha256).toHex(); }
QByteArray readFile(const QString& path) {
  QFile f(path); if (!f.open(QIODevice::ReadOnly)) throw std::runtime_error("cannot read " + path.toStdString());
  return f.readAll();
}
void writeFile(const QString& path, const QByteArray& data) {
  QFile f(path); if (!f.open(QIODevice::WriteOnly|QIODevice::Truncate)) throw std::runtime_error("cannot write " + path.toStdString());
  f.write(data);
}
Vector sub(const Vector& a, const Vector& b) { return {a[0]-b[0],a[1]-b[1],a[2]-b[2]}; }
Vector cross(const Vector& a, const Vector& b) { return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]}; }
double dot(const Vector& a, const Vector& b) { return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]; }
Vector perp(const Vector& v, const Vector& axis) { const double k = dot(v,axis); return {v[0]-k*axis[0],v[1]-k*axis[1],v[2]-k*axis[2]}; }

// --- configuration labels (written to labels.json before any plan) --------------------------------
struct Label { QString wrist, elbow, shoulder; int turn4 = 0, turn6 = 0; };
const char* labelMethod =
  "Joint axes z_i (unit) and origins p_i in the robot base from kinematics::forwardLinks (the planner's chain). "
  "Wrist centre pw = foot on the J4 axis of the common perpendicular between the J4 and J5 axes (does not move "
  "with q4, q5, q6; equals p5 when the axes meet; p5 if the axes are parallel). "
  "wrist = sign(z5 . (z4 x z6)), '?' if |z4 x z6| < sin(1 deg). "
  "elbow = sign(z2 . ((p3-p2) x (pw-p3))), '?' if |z2 . ((p3-p2) x (pw-p3))| / (|p3-p2| |pw-p3|) < sin(1 deg). "
  "shoulder = sign(d . f) with d = component of (pw-p1) perpendicular to z1 and f = unit(z2 x z1), "
  "'?' if |d . f| < 1 mm or |z2 x z1| < 0.1. turn4 = floor((q4+180)/360), turn6 = floor((q6+180)/360).";
QString sign(double v) { return v > 0 ? "+" : "-"; }
Label label(const program::Geometry& g, const ProgramJoints& q) {
  const auto frames = kinematics::forwardLinks(g.chain,{q.begin(),q.end()});
  std::array<Vector,6> z{}, p{};
  for (std::size_t i = 0; i < 6; ++i) {
    const auto& m = frames[i]; const auto axis = *g.chain.links[i].axis; Vector w{};
    for (std::size_t r = 0; r < 3; ++r) { for (std::size_t c = 0; c < 3; ++c) w[r] += m[c*4+r]*axis[c]; p[i][r] = m[12+r]; }
    const double n = program::norm(w); z[i] = {w[0]/n,w[1]/n,w[2]/n};
  }
  Label l; Vector pw = p[4];
  {  // closest point on line (p4, z4) to line (p5, z5)
    const auto w0 = sub(p[3],p[4]); const double b = dot(z[3],z[4]), dd = dot(z[3],w0), e = dot(z[4],w0);
    const double den = 1-b*b;
    if (den > 1e-12) { const double t = (b*e-dd)/den; pw = {p[3][0]+t*z[3][0],p[3][1]+t*z[3][1],p[3][2]+t*z[3][2]}; }
  }
  const auto c46 = cross(z[3],z[5]);
  l.wrist = program::norm(c46) < wristBandSin ? "?" : sign(dot(z[4],c46));
  const auto a = sub(p[2],p[1]), b = sub(pw,p[2]), cab = cross(a,b);
  const double denom = program::norm(a)*program::norm(b);
  l.elbow = denom <= 0 || std::abs(dot(z[1],cab))/denom < wristBandSin ? "?" : sign(dot(z[1],cab));
  const auto d = perp(sub(pw,p[0]),z[0]); const auto f = cross(z[1],z[0]); const double fn = program::norm(f);
  const Vector fu{f[0]/fn,f[1]/fn,f[2]/fn};
  l.shoulder = fn < .1 || std::abs(dot(d,fu)) < 1e-3 ? "?" : sign(dot(d,fu));
  l.turn4 = static_cast<int>(std::floor((q[3]+180)/360)); l.turn6 = static_cast<int>(std::floor((q[5]+180)/360));
  return l;
}
QJsonObject json(const Label& l) {
  return {{"wrist",l.wrist},{"elbow",l.elbow},{"shoulder",l.shoulder},{"turn4",l.turn4},{"turn6",l.turn6}};
}
bool undetermined(const Label& l) { return l.wrist == "?" || l.elbow == "?" || l.shoulder == "?"; }
bool sameLabels(const Label& a, const Label& b) {
  return !undetermined(a) && !undetermined(b) && a.wrist == b.wrist && a.elbow == b.elbow &&
         a.shoulder == b.shoulder && a.turn4 == b.turn4 && a.turn6 == b.turn6;
}

// --- path parameter s per sample (same trapezoid as the planner, robot_program_planner.cpp) -------------
struct Profile { double distance = 0, acceleration = 1, ramp = 0, flat = 0, velocity = 0;
  double duration() const { return 2*ramp+flat; }
  double fraction(double t) const {
    if (distance == 0) return 1; t = std::clamp(t,0.,duration());
    if (t < ramp) return .5*acceleration*t*t/distance;
    if (t < ramp+flat) return (velocity*(t-ramp)+.5*velocity*ramp)/distance;
    const double r = duration()-t; return 1-.5*acceleration*r*r/distance; } };
Profile profile(double distance, double velocity, double acceleration) {
  Profile p; p.distance = distance; p.acceleration = acceleration; if (distance == 0) return p;
  p.ramp = std::min(velocity/acceleration,std::sqrt(distance/acceleration)); p.velocity = p.ramp*acceleration;
  p.flat = std::max(0.,distance/p.velocity-p.ramp); return p;
}
std::vector<double> pathParameter(const program::Geometry& g, const RobotProgramSettings& st,
                                  const ProgramJoints& start, const ProgramJoints& target, std::size_t samples) {
  const auto a = program::forward(g,start), b = program::forward(g,target);
  const double mm = program::norm(sub(b.position,a.position))*1000;
  const double deg = program::norm(program::rotationError(a.rotation,b.rotation))/program::radiansPerDegree;
  double v = 1e100, acc = 1e100;
  if (mm > 1e-12) { v = st.linearVel/mm; acc = st.linearAcc/mm; }
  if (deg > 1e-12) { v = std::min(v,st.angularVel/deg); acc = std::min(acc,st.angularAcc/deg); }
  const auto line = profile(mm > 1e-12 || deg > 1e-12 ? 1 : 0,v,acc); const double duration = line.duration();
  const auto ticks = static_cast<std::size_t>(std::ceil(duration/robotProgramInterval));
  if (ticks+1 != samples) throw std::runtime_error("path parameter: sample count differs from the planner");
  std::vector<double> s(samples,0.);
  for (std::size_t i = 1; i < samples; ++i)
    s[i] = line.fraction(duration*(static_cast<double>(i)/static_cast<double>(ticks)));  // planner: duration*phase
  return s;
}

// --- strategies ------------------------------------------------------------------------------
using Seed = std::function<ProgramJoints(std::size_t, const ProgramJoints&)>;
RobotProgramPlan resolve(const RobotProgramPlan& base, const program::Geometry& g, const RobotDefinition& d, const Seed& seed) {
  RobotProgramPlan out = base;
  for (std::size_t i = 1; i < out.samples.size(); ++i) {
    auto& s = out.samples[i];
    if (s.kind != RobotStepKind::Lin) continue;
    const auto sol = program::inverse(g,d,s.desired,seed(i,out.samples[i-1].joints));
    s.joints = sol.joints; s.ikFailure = sol.failure;
    s.positionErrorMm = sol.positionErrorMm; s.orientationErrorDeg = sol.orientationErrorDeg;
  }
  return out;
}
bool bitIdentical(const RobotProgramPlan& a, const RobotProgramPlan& b) {
  if (a.samples.size() != b.samples.size()) return false;
  for (std::size_t i = 0; i < a.samples.size(); ++i)
    if (std::memcmp(a.samples[i].joints.data(),b.samples[i].joints.data(),sizeof(ProgramJoints)) != 0 ||
        a.samples[i].ikFailure != b.samples[i].ikFailure) return false;
  return true;
}

// --- one result row ------------------------------------------------------------------------------
QString findingName(RobotCheckKind k) {
  switch (k) {
    case RobotCheckKind::EndpointMismatch: return "end_joint_mismatch";
    case RobotCheckKind::OutOfReach: case RobotCheckKind::SolverFailure: return "ik_fail";
    case RobotCheckKind::JointSpeed: return "joint_speed";
    case RobotCheckKind::JointAcceleration: return "joint_accel";
    case RobotCheckKind::Manipulability: return "manipulability";
    case RobotCheckKind::LineDeviation: return "line_deviation";
    case RobotCheckKind::JointLimit: return "other_joint_limit";
  }
  return "other_unknown";
}
struct Row { QJsonObject json; bool mismatch = false, converged = true; QString V, T, Vcfg, type; Label end; };
QString typeOf(bool mismatch, bool converged, const Label& end, const Label& target, const ProgramJoints& e, const ProgramJoints& t) {
  if (!mismatch) return {};
  if (!converged) return "e";
  if (undetermined(end) || undetermined(target)) return "x";
  if (end.elbow != target.elbow || end.shoulder != target.shoulder) return "c";
  if (end.wrist != target.wrist) return "b";
  for (std::size_t j : {0u,1u,2u,4u}) if (std::abs(e[j]-t[j]) > tolJoint) return "d";
  bool nonzero = false;
  for (std::size_t j : {3u,5u}) {
    const double diff = e[j]-t[j]; const double n = std::round(diff/360.);
    if (std::abs(diff-360.*n) > tolJoint) return "d";
    nonzero = nonzero || n != 0;
  }
  return nonzero ? "a" : "d";
}
Row makeRow(const QString& model, int k, const QString& solver, const QString& speed, int round,
            const ProgramJoints& start, const ProgramJoints& target, const RobotProgramPlan& plan,
            const program::Geometry& g, const RobotDefinition& d, const std::vector<double>& s,
            const Label& startL, const Label& targetL) {
  Row r; const auto& end = plan.samples.back().joints;
  QJsonArray over; for (std::size_t j = 0; j < 6; ++j) { const bool o = std::abs(end[j]-target[j]) > tolJoint; over.append(o); r.mismatch = r.mismatch || o; }
  r.converged = plan.solved();
  int fails = 0; int unreachable = 0, atLimit = 0, budget = 0;
  for (const auto& smp : plan.samples) {
    if (smp.ikFailure == program::IkFailure::None) continue;
    ++fails;
    if (smp.ikFailure == program::IkFailure::OutOfReach) { ++unreachable; continue; }
    bool limit = false;
    for (std::size_t j = 0; j < 6; ++j)
      limit = limit || std::abs(smp.joints[j]-d.joints[j].minimumDegrees) < 1e-9 || std::abs(smp.joints[j]-d.joints[j].maximumDegrees) < 1e-9;
    if (limit) ++atLimit; else ++budget;
  }
  const auto fe = program::forward(g,end); const auto ft = program::forward(g,target);
  const double posErr = program::norm(sub(fe.position,ft.position))*1000;
  const double rotErr = program::norm(program::rotationError(fe.rotation,ft.rotation))/program::radiansPerDegree;
  double maxStep = 0; int maxJoint = 0; std::size_t maxIndex = 0; double j4 = 0, j6 = 0, manip = 1e300;
  for (std::size_t i = 0; i < plan.samples.size(); ++i) {
    manip = std::min(manip,program::manipulability(program::jacobian(g,plan.samples[i].joints)));
    if (i == 0) continue;
    for (std::size_t j = 0; j < 6; ++j) {
      const double dq = std::abs(plan.samples[i].joints[j]-plan.samples[i-1].joints[j]);
      if (dq > maxStep) { maxStep = dq; maxJoint = static_cast<int>(j)+1; maxIndex = i; }
    }
    j4 += std::abs(plan.samples[i].joints[3]-plan.samples[i-1].joints[3]);
    j6 += std::abs(plan.samples[i].joints[5]-plan.samples[i-1].joints[5]);
  }
  const auto check = checkRobotProgram(plan,d);
  std::map<QString,std::pair<int,int>> counts{{"end_joint_mismatch",{0,0}},{"ik_fail",{0,0}},{"joint_speed",{0,0}}};
  for (const auto& f : check.findings) {
    auto& c = counts[findingName(f.kind)];
    (f.severity == RobotCheckSeverity::Block ? c.second : c.first) += 1;
  }
  QJsonObject findings; int blocks = 0, blocksNoEnd = 0;
  for (const auto& [name,c] : counts) {
    findings[name] = QJsonObject{{"warn",c.first},{"block",c.second}};
    blocks += c.second; if (name != "end_joint_mismatch") blocksNoEnd += c.second;
  }
  r.end = label(g,end);
  r.V = blocks == 0 && fails == 0 && r.converged ? "allow" : "block";
  r.T = blocksNoEnd == 0 && fails == 0 && r.converged && posErr <= tolPos && rotErr <= tolRot ? "allow" : "block";
  r.Vcfg = sameLabels(startL,targetL) ? r.T : "block";
  r.type = typeOf(r.mismatch,r.converged,r.end,targetL,end,target);
  r.json = QJsonObject{
    {"model",model},{"k",k},{"solver",solver},{"speed",speed},{"plan_round",round},
    {"start_deg",six(start)},{"target_deg",six(target)},{"end_deg",six(end)},{"end_over_001",over},
    {"end_label",json(r.end)},{"converged",r.converged},{"samples",static_cast<qint64>(plan.samples.size())},
    {"ik_fail_samples",fails},{"ik_fail_causes",QJsonObject{{"unreachable",unreachable},{"limit",atLimit},{"budget",budget}}},
    {"end_pos_err_mm",posErr},{"end_rot_err_deg",rotErr},{"end_iters",-1},
    {"max_step_deg",maxStep},{"max_step_joint",maxJoint},{"max_step_index",static_cast<qint64>(maxIndex)},
    {"max_step_s",s[maxIndex]},{"j4_travel_deg",j4},{"j6_travel_deg",j6},{"min_manipulability",manip},
    {"max_speed_ratio",check.maximumSpeedRatio},{"findings",findings},
    {"verdict",QJsonObject{{"V",r.V},{"T",r.T},{"V_cfg",r.Vcfg}}},
    {"mismatch",r.mismatch},{"type",r.type.isEmpty() ? QJsonValue() : QJsonValue(r.type)},
    {"plan_hash",QString::fromStdString(robotProgramPlanHash(plan))}};
  return r;
}

RobotProgram linProgram(const ProgramJoints& target, double speedFactor) {
  RobotProgram p; p.settings.linearVel *= speedFactor; p.settings.angularVel *= speedFactor;
  p.steps.push_back({.kind=RobotStepKind::Lin,.target=target}); return p;
}

// --- summary (counted from this runner's own row fields; the independent check re-derives) ----------
QString word(bool decidable, bool ok, const char* yes = "맞음", const char* no = "틀림") {
  return !decidable ? "판정 불가" : ok ? yes : no;
}
}  // namespace

int main(int argc, char** argv) {
  try {
    QString inputsPath, outDir, productCommit, runnerCommit = "uncommitted"; bool dev = false, precheckOnly = false;
    for (int i = 1; i < argc; ++i) {
      const std::string a = argv[i];
      auto next = [&]() { if (i+1 >= argc) throw std::runtime_error("missing value for " + a); return QString::fromLocal8Bit(argv[++i]); };
      if (a == "--inputs") inputsPath = next(); else if (a == "--out") outDir = next();
      else if (a == "--product-commit") productCommit = next(); else if (a == "--runner-commit") runnerCommit = next();
      else if (a == "--dev") dev = true; else if (a == "--precheck-only") precheckOnly = true;
      else throw std::runtime_error("unknown argument " + a);
    }
    if (outDir.isEmpty() || (!precheckOnly && inputsPath.isEmpty())) {
      std::cerr << "usage: vexplor_robot_program_tr06 --inputs <list> --out <dir> --product-commit <sha> [--runner-commit <sha>] [--dev] [--precheck-only]\n";
      return 2;
    }
    auto hex40 = [](const QString& v) { static const QRegularExpression re("^[0-9a-f]{40}$"); return re.match(v).hasMatch(); };
    if (!dev && !precheckOnly) {
      if (productCommit != "e2dc7a7846a59952fb6c76d63b89137bef5129ab") throw std::runtime_error("product commit must be e2dc7a7846a59952fb6c76d63b89137bef5129ab");
      if (!hex40(runnerCommit)) throw std::runtime_error("--runner-commit must be a 40-hex commit for an official run");
    }
    QDir().mkpath(outDir);
    const auto catalog = robotCatalog();
    if (catalog.size() != 12) throw std::runtime_error("expected 12 catalog models");
    const RobotDefinition* abb = nullptr;
    for (const auto& d : catalog) if (QString::fromUtf8(d.id.data(),static_cast<int>(d.id.size())).contains("abb",Qt::CaseInsensitive)) abb = &d;
    if (!abb) throw std::runtime_error("model A (ABB) not found in catalog");
    auto idOf = [](const RobotDefinition& d) { return QString::fromUtf8(d.id.data(),static_cast<int>(d.id.size())); };
    auto inLimits = [](const RobotDefinition& d, const ProgramJoints& q) {
      for (std::size_t j = 0; j < 6; ++j) if (q[j] < d.joints[j].minimumDegrees || q[j] > d.joints[j].maximumDegrees) return false;
      return true; };

    // ---- pre-checks (model A) ----
    auto runPrecheck = [&](QJsonObject& precheck, bool& bitAll) {
    struct Pre { const char* key; const char* expect; ProgramJoints start, target; };
    ProgramJoints neg = readyPose; neg[5] = 90; ProgramJoints turn = readyPose; turn[5] = 270;
    // Positive 2 = ready pose with J5 +30 -> -30 and J4 0 -> 10. A J5-only move passes the wrist singularity
    // exactly and is followed continuously (no mismatch), so J4 is moved by 10 deg to keep the line off it.
    const ProgramJoints ws{0,-35,55,0,30,0}; const ProgramJoints wt{0,-35,55,10,-30,0};
    const std::vector<Pre> pres{{"negative","none",readyPose,neg},{"positive_turn","a",readyPose,turn},{"positive_wrist","b",ws,wt}};
    QJsonObject preInputs;
    {
      const auto g = program::geometry(*abb,{});
      for (const auto& pc : pres) {
        if (!inLimits(*abb,pc.start) || !inLimits(*abb,pc.target)) throw std::runtime_error("pre-check input outside model A joint limits");
        const auto p = linProgram(pc.target,1); const auto plan = planRobotProgram(p,*abb,pc.start);
        const auto s = pathParameter(g,p.settings,pc.start,pc.target,plan.samples.size());
        const auto sl = label(g,pc.start), tl = label(g,pc.target);
        const auto row = makeRow("A",-1,"C0","base",1,pc.start,pc.target,plan,g,*abb,s,sl,tl);
        const auto again = resolve(plan,g,*abb,[](std::size_t, const ProgramJoints& prev) { return prev; });
        bitAll = bitAll && bitIdentical(plan,again);
        precheck[pc.key] = QJsonObject{{"expect",pc.expect},{"got",row.type.isEmpty() ? QString("none") : row.type}};
        preInputs[pc.key] = QJsonObject{{"start_deg",six(pc.start)},{"target_deg",six(pc.target)}};
      }
    }
    precheck["inputs"] = preInputs;
    };
    auto precheckOk = [&](const QJsonObject& pc) {
      for (const char* k : {"negative","positive_turn","positive_wrist"})
        if (pc[k].toObject()["expect"] != pc[k].toObject()["got"]) return false;
      return true; };
    if (precheckOnly) {
      QJsonObject precheck; bool bitAll = true; runPrecheck(precheck,bitAll);
      precheck["c0_bit_identical"] = bitAll;
      writeFile(outDir+"/precheck.json",QJsonDocument(precheck).toJson(QJsonDocument::Indented));
      std::cout << QJsonDocument(precheck).toJson(QJsonDocument::Indented).toStdString();
      return precheckOk(precheck) && bitAll ? 0 : 3;
    }

    // ---- inputs ----
    const auto inputsBytes = readFile(inputsPath); const auto inputsSha = sha256(inputsBytes);
    if (!dev && inputsSha != expectedInputsSha) throw std::runtime_error("input list sha256 differs from the fixed value (use --dev only for development inputs)");
    const auto inputsDoc = QJsonDocument::fromJson(inputsBytes).object();
    if (!dev && inputsDoc["purpose"].toString() != "confirm") throw std::runtime_error("not the confirmation input list");
    struct Input { int k; QString group; ProgramJoints start, target; };
    std::vector<Input> inputs;
    for (const auto& v : inputsDoc["inputs"].toArray()) {
      const auto o = v.toObject(); inputs.push_back({o["k"].toInt(),o["group"].toString(),joints(o["start_deg"]),joints(o["target_deg"])});
    }
    bool limitsInputs = true;
    for (const auto& d : catalog) for (const auto& in : inputs) limitsInputs = limitsInputs && inLimits(d,in.start) && inLimits(d,in.target);
    bool limitsE1 = true;
    for (const auto& d : catalog) for (std::size_t j = 0; j < 6; ++j) for (int m = 1; m <= 40; ++m) {
      const double dist = d.joints[j].maximumSpeedDegrees*(.1+.004*m);
      const double dir = (d.joints[j].maximumDegrees-readyPose[j]) >= (readyPose[j]-d.joints[j].minimumDegrees) ? 1 : -1;
      auto e = readyPose; e[j] += dir*dist; limitsE1 = limitsE1 && inLimits(d,readyPose) && inLimits(d,e);
    }
    QJsonObject run{{"schema","tr06-run/v1"},{"run_id",QFileInfo(outDir).fileName()},{"product_commit",productCommit},
                    {"runner_commit",runnerCommit},{"inputs_sha256",QString::fromLatin1(inputsSha)},
                    {"compiler",QString::fromLatin1(__VERSION__)},{"started_utc",utcNow()},
                    {"limits_ok_inputs",limitsInputs},{"limits_ok_e1",limitsE1},{"dev",dev}};
    if (!limitsInputs || !limitsE1) {
      writeFile(outDir+"/run.json",QJsonDocument(run).toJson(QJsonDocument::Indented));
      throw std::runtime_error("joint limits check failed — no plan made");
    }

    // ---- labels before any plan ----
    std::map<std::pair<QString,int>,std::pair<Label,Label>> labels; QJsonArray labelRows;
    for (const auto& d : catalog) {
      const auto g = program::geometry(d,{});
      for (const auto& in : inputs) {
        const auto sl = label(g,in.start), tl = label(g,in.target);
        labels[{idOf(d),in.k}] = {sl,tl};
        labelRows.append(QJsonObject{{"model",idOf(d)},{"k",in.k},{"start",json(sl)},{"target",json(tl)}});
      }
    }
    const auto labelsBytes = QJsonDocument(QJsonObject{{"schema","tr06-labels/v1"},{"method",labelMethod},
      {"wrist_band_deg",1.0},{"elbow_band_deg",1.0},{"shoulder_band_mm",1.0},{"labels",labelRows}}).toJson(QJsonDocument::Indented);
    writeFile(outDir+"/labels.json",labelsBytes);
    run["labels_written_utc"] = utcNow(); run["labels_sha256"] = QString::fromLatin1(sha256(labelsBytes));
    std::this_thread::sleep_for(std::chrono::milliseconds(5));  // first_plan_utc strictly after labels_written_utc
    run["first_plan_utc"] = utcNow();
    QJsonObject precheck; bool bitAll = true; runPrecheck(precheck,bitAll);  // after labels: no plan precedes labels

    // ---- main loop ----
    QByteArray results;
    struct Agg { int n = 0, x = 0; };
    std::map<QString,Agg> agg;  // keys described where used
    auto add = [&](const QString& key, bool hit) { auto& a = agg[key]; ++a.n; if (hit) ++a.x; };
    int p7excluded = 0; std::vector<std::string> selfInvalid;
    for (const auto& d : catalog) {
      const auto g = program::geometry(d,{}); const auto id = idOf(d);
      for (const auto& in : inputs) {
        const auto& [sl,tl] = labels[{id,in.k}];
        const auto p = linProgram(in.target,1);
        const auto c0 = planRobotProgram(p,d,in.start), c0b = planRobotProgram(p,d,in.start);
        const auto half = planRobotProgram(linProgram(in.target,.5),d,in.start);
        const auto s = pathParameter(g,p.settings,in.start,in.target,c0.samples.size());
        const auto sHalf = pathParameter(g,linProgram(in.target,.5).settings,in.start,in.target,half.samples.size());
        bitAll = bitAll && bitIdentical(c0,resolve(c0,g,d,[](std::size_t, const ProgramJoints& prev) { return prev; }));
        const auto target = in.target; const auto start = in.start;
        const auto c1 = resolve(c0,g,d,[&](std::size_t, const ProgramJoints&) { return target; });
        const auto c2 = resolve(c0,g,d,[&](std::size_t, const ProgramJoints&) { return readyPose; });
        const auto c3 = resolve(c0,g,d,[&](std::size_t i, const ProgramJoints&) {
          ProgramJoints q{}; for (std::size_t j = 0; j < 6; ++j) q[j] = start[j]+(target[j]-start[j])*s[i]; return q; });
        const auto c2z = resolve(c0,g,d,[](std::size_t, const ProgramJoints&) { return ProgramJoints{}; });
        const std::vector<std::tuple<QString,QString,int,const RobotProgramPlan*,const std::vector<double>*>> plans{
          {"C0","base",1,&c0,&s},{"C0","base",2,&c0b,&s},{"C0","half",1,&half,&sHalf},
          {"C1","base",1,&c1,&s},{"C2","base",1,&c2,&s},{"C3","base",1,&c3,&s},{"C2z","base",1,&c2z,&s}};
        if (!bitIdentical(c0,c0b) || robotProgramPlanHash(c0) != robotProgramPlanHash(c0b)) selfInvalid.push_back("C0 plans differ " + id.toStdString() + " k=" + std::to_string(in.k));
        for (const auto& [solver,speed,round,plan,sp] : plans) {
          const auto row = makeRow(id,in.k,solver,speed,round,in.start,in.target,*plan,g,d,*sp,sl,tl);
          if ((solver == "C1" || solver == "C3") && row.mismatch) selfInvalid.push_back(solver.toStdString() + " end mismatch " + id.toStdString() + " k=" + std::to_string(in.k));
          if (solver == "C0" && row.mismatch && row.converged &&
              !(row.json["end_pos_err_mm"].toDouble() <= tolPos && row.json["end_rot_err_deg"].toDouble() <= tolRot))
            selfInvalid.push_back("converged C0 mismatch fails end pose " + id.toStdString() + " k=" + std::to_string(in.k));
          results += QJsonDocument(row.json).toJson(QJsonDocument::Compact) + "\n";
          if (speed != "base" || round != 1) continue;
          const bool cross = in.group == "cross";
          if (solver == "C0") {
            add(cross ? "P1" : "P2",row.mismatch);
            if (row.mismatch) add("P3",row.T == "allow");
            if (undetermined(sl) || undetermined(tl)) ++p7excluded;
            else {
              if (sl.wrist != tl.wrist) add("P7a",row.mismatch);
              if (sameLabels(sl,tl)) add("P7b",row.mismatch);
            }
          }
          if (cross && solver == "C1") add("P5",row.V == "allow");
          if (cross && solver == "C3") add("P6",row.V == "allow");
          if (cross && (solver == "C1" || solver == "C2" || solver == "C3")) add("F3_"+solver,!row.mismatch && row.V == "allow");
        }
      }
    }
    writeFile(outDir+"/results.jsonl",results);

    // ---- E1 ----
    QByteArray e1;
    for (const auto& d : catalog) for (std::size_t j = 0; j < 6; ++j) for (int m = 1; m <= 40; ++m) {
      const double vmax = d.joints[j].maximumSpeedDegrees, dist = vmax*(.1+.004*m);
      const double dir = (d.joints[j].maximumDegrees-readyPose[j]) >= (readyPose[j]-d.joints[j].minimumDegrees) ? 1 : -1;
      RobotProgram p; p.settings.jointVel = 100; p.settings.jointAcc = 10*vmax;
      auto target = readyPose; target[j] += dir*dist;
      p.steps.push_back({.kind=RobotStepKind::Joint,.target=target});
      const auto plan = planRobotProgram(p,d,readyPose); const auto check = checkRobotProgram(plan,d);
      const double ratio = check.maximumSpeedRatio;
      e1 += QJsonDocument(QJsonObject{{"model",idOf(d)},{"joint",static_cast<int>(j)+1},{"m",m},{"max_speed_ratio",ratio},
        {"block_strict",ratio > 1},{"block_margin",ratio > speedMargin},{"start_deg",six(readyPose)},
        {"distance_deg",dist},{"duration_s",plan.samples.back().seconds()},{"accel_deg_s2",10*vmax}}).toJson(QJsonDocument::Compact) + "\n";
    }
    writeFile(outDir+"/e1.jsonl",e1);

    // ---- summary ----
    auto g = [&](const char* k) { return agg[k]; };
    auto pr = [&](const char* k, bool atLeast, int num, int den) {
      const auto a = g(k); const bool ok = atLeast ? den*a.x >= num*a.n : den*a.x <= num*a.n;
      return QJsonObject{{"x",a.x},{"n",a.n},{"verdict",word(a.n > 0,ok)}}; };
    QJsonObject pred;
    pred["P1"] = pr("P1",true,4,5); pred["P2"] = pr("P2",false,1,5); pred["P3"] = pr("P3",true,3,10);
    pred["P5"] = pr("P5",false,1,5); pred["P6"] = pr("P6",false,1,5);
    pred["P7a"] = pr("P7a",true,19,20); pred["P7b"] = pr("P7b",false,1,20);
    const auto v7a = pred["P7a"].toObject()["verdict"].toString(), v7b = pred["P7b"].toObject()["verdict"].toString();
    pred["P7"] = QJsonObject{{"verdict",(v7a == "틀림" || v7b == "틀림") ? "틀림" : (v7a == "판정 불가" || v7b == "판정 불가") ? "판정 불가" : "맞음"},
                             {"excluded_x",p7excluded}};
    const auto p1 = g("P1"), p2 = g("P2"), p3 = g("P3");
    const bool f1ok = 10LL*(static_cast<long long>(p1.x)*p2.n-static_cast<long long>(p2.x)*p1.n) < 3LL*p1.n*p2.n;
    pred["F1"] = QJsonObject{{"x_cross",p1.x},{"n_cross",p1.n},{"x_noncross",p2.x},{"n_noncross",p2.n},
                             {"verdict",word(p1.n > 0 && p2.n > 0,f1ok,"성립","불성립")}};
    pred["F2"] = QJsonObject{{"x",p3.x},{"n",p3.n},{"verdict",word(p3.n > 0,10*p3.x < p3.n,"성립","불성립")}};
    QJsonObject by; QStringList words;
    for (const char* sv : {"C1","C2","C3"}) {
      const auto a = g((std::string("F3_")+sv).c_str()); const auto w = word(a.n > 0,2*a.x >= a.n,"성립","불성립");
      by[sv] = QJsonObject{{"x",a.x},{"n",a.n},{"verdict",w}}; words << w;
    }
    pred["F3"] = QJsonObject{{"by_solver",by},{"verdict",words.contains("성립") ? "성립" : words.contains("판정 불가") ? "판정 불가" : "불성립"}};
    writeFile(outDir+"/summary.json",QJsonDocument(QJsonObject{{"schema","tr06-summary/v1"},{"predictions",pred}}).toJson(QJsonDocument::Indented));

    precheck["c0_bit_identical"] = bitAll;
    writeFile(outDir+"/precheck.json",QJsonDocument(precheck).toJson(QJsonDocument::Indented));
    run["finished_utc"] = utcNow();
    writeFile(outDir+"/run.json",QJsonDocument(run).toJson(QJsonDocument::Indented));
    std::cout << "rows " << results.count('\n') << " e1 " << e1.count('\n') << " c0_bit_identical " << bitAll << "\n";
    if (!bitAll || !precheckOk(precheck) || !selfInvalid.empty()) {
      for (const auto& m : selfInvalid) std::cerr << "invalid: " << m << "\n";
      std::cerr << "tr06 runner: invalid run (see precheck.json / stderr)\n";
      return 3;
    }
    return 0;
  } catch (const std::exception& e) {
    std::cerr << "tr06 runner: " << e.what() << "\n";
    return 1;
  }
}
