//
// Code auto-generated by cxsetup (XSPEC12 local 
// model package code generator).  Do not edit.
// Package: 
// Function header: functionMap.h

#ifndef    FUNCTIONMAP_H
#define    FUNCTIONMAP_H

#include    <XSFunctions/Utilities/funcType.h>

class    XSModelFunction;

extern    ModelFunctionMap  XSFunctionMap;

void  createFunctionMap();
void  clearFunctionMap();

extern "C"  {


	XSCCall      agauss;
	xsf77Call    agnsed_;
	XSCCall      apec;
	XSCCall      bapec;
	XSCCall      btapec;
	xsf77Call    xsblbd_;
	xsf77Call    xsbbrd_;
	XSCCall      xsbexrav;
	XSCCall      xsbexriv;
	XSCCall      brokenPowerLaw;
	XSCCall      broken2PowerLaw;
	xsf77Call    xsbmc_;
	xsf77Call    xsbrms_;
	XSCCall      brnei;
	XSCCall      bvapec;
	XSCCall      bvrnei;
	XSCCall      bvtapec;
	XSCCall      bvvapec;
	XSCCall      bvvrnei;
	XSCCall      bvvtapec;
	XSCCall      c6mekl;
	XSCCall      c6pmekl;
	XSCCall      c6pvmkl;
	XSCCall      c6vmekl;
	XSCCall      carbatm;
	xsf77Call    cemekl_;
	XSCCall      cemVMekal;
	XSCCall      xscflw;
	xsf77Call    compbb_;
	xsccCall     xscompmag;
	xsf77Call    compls_;
	XSCCall      xscompps;
	xsf77Call    compst_;
	xsccCall     xscomptb;
	XSCCall      xscompth;
	xsf77Call    xstitg_;
	XSCCall      cph;
	XSCCall      cplinear;
	XSCCall      cutoffPowerLaw;
	xsf77Call    disk_;
	xsf77Call    diskir_;
	xsf77Call    xsdskb_;
	XSCCall      diskline;
	xsf77Call    diskm_;
	xsf77Call    disko_;
	xsf77Call    diskpbb_;
	xsf77Call    xsdiskpn_;
	xsf77Call    eplogpar_;
	XSCCall      xseqpair;
	XSCCall      xseqth;
	XSCCall      equil;
	xsf77Call    xsxpdec_;
	xsf77Call    ezdiskbb_;
	XSCCall      gaussianLine;
	XSCCall      gaussDem;
	XSCCall      gnei;
	xsf77Call    grad_;
	xsccCall     xsgrbcomp;
	xsf77Call    xsgrbm_;
	XSCCall      hatm;
	xsf77Call    jet_;
	XSCCall      kerrbb;
	XSCCall      kerrd;
	XSCCall      spin;
	xsf77Call    kyconv_;
	xsf77Call    kyrline_;
	XSCCall      laor;
	XSCCall      laor2;
	XSCCall      logpar;
	XSCCall      lorentzianLine;
	XSCCall      meka;
	XSCCall      mekal;
	XSCCall      xsmkcf;
	XSCCall      nei;
	XSCCall      nlapec;
	XSCCall      npshock;
	xsf77Call    nsa_;
	xsf77Call    nsagrav_;
	xsf77Call    nsatmos_;
	XSCCall      nsmax;
	XSCCall      nsmaxg;
	XSCCall      nsx;
	XSCCall      xsnteea;
	XSCCall      nthcomp;
	xsf77Call    optxagn_;
	xsf77Call    optxagnf_;
	xsf77Call    xspegp_;
	xsf77Call    pexmon_;
	XSCCall      xspexrav;
	XSCCall      xspexriv;
	xsf77Call    xsp1tr_;
	XSCCall      powerLaw;
	xsf77Call    xsposm_;
	XSCCall      pshock;
	xsf77Call    qsosed_;
	XSCCall      raysmith;
	xsf77Call    xredge_;
	xsf77Call    xsrefsch_;
	XSCCall      rnei;
	XSCCall      sedov;
	XSCCall      sirf;
	xsccCall     slimbbmodel;
	xsccCall     xsmaug;
	XSCCall      snapec;
	xsf77Call    srcut_;
	xsf77Call    sresc_;
	xsf77Call    ssa_;
	xsf77Call    xsstep_;
	XSCCall      tapec;
	XSCCall      vapec;
	xsf77Call    xsbrmv_;
	XSCCall      vcph;
	XSCCall      vequil;
	XSCCall      vgaussDem;
	XSCCall      vgnei;
	XSCCall      vmeka;
	XSCCall      vmekal;
	XSCCall      xsvmcf;
	XSCCall      vnei;
	XSCCall      vnpshock;
	XSCCall      voigtLine;
	XSCCall      vpshock;
	XSCCall      vraysmith;
	XSCCall      vrnei;
	XSCCall      vsedov;
	XSCCall      vtapec;
	XSCCall      vvapec;
	XSCCall      vvgnei;
	XSCCall      vvnei;
	XSCCall      vvnpshock;
	XSCCall      vvpshock;
	XSCCall      vvrnei;
	XSCCall      vvsedov;
	XSCCall      vvtapec;
	XSCCall      zagauss;
	xsf77Call    xszbod_;
	XSCCall      zBrokenPowerLaw;
	xsf77Call    xszbrm_;
	XSCCall      zcutoffPowerLaw;
	XSCCall      xszgau;
	XSCCall      zLogpar;
	XSCCall      zpowerLaw;
	XSCCall      xsabsori;
	XSCCall      acisabs;
	xsf77Call    xscnst_;
	xsf77Call    xscabs_;
	xsf77Call    xscycl_;
	xsf77Call    xsdust_;
	xsf77Call    xsedge_;
	xsf77Call    xsabsc_;
	xsf77Call    xsexp_;
	XSCCall      gaussianAbsorptionLine;
	xsf77Call    xsphei_;
	xsf77Call    xshecu_;
	xsf77Call    xshrfl_;
	xsf77Call    ismabs_;
	xsf77Call    xslyman_;
	xsf77Call    xsntch_;
	xsf77Call    xsabsp_;
	xsf77Call    xsphab_;
	xsf77Call    xsplab_;
	XSCCall      xspwab;
	xsf77Call    xscred_;
	xsf77Call    xssmdg_;
	XSCCall      superExpCutoff;
	xsf77Call    xsspln_;
	xsf77Call    xssssi_;
	XSCCall      swind1;
	XSCCall      tbabs;
	XSCCall      tbfeo;
	XSCCall      tbgas;
	XSCCall      tbgrain;
	XSCCall      tbvabs;
	XSCCall      tbpcf;
	XSCCall      tbrel;
	xsf77Call    xsred_;
	xsf77Call    xsabsv_;
	xsf77Call    xsvphb_;
	xsf77Call    xsabsw_;
	xsf77Call    xswnab_;
	xsf77Call    xsxirf_;
	XSCCall      xscatmodel;
	xsccCall     xszbabs;
	xsf77Call    mszdst_;
	xsf77Call    xszedg_;
	xsf77Call    xszhcu_;
	xsf77Call    zigm_;
	xsf77Call    xszabp_;
	xsf77Call    xszphb_;
	XSCCall      zxipcf;
	xsf77Call    xszcrd_;
	xsf77Call    msldst_;
	XSCCall      ztbabs;
	xsf77Call    xszvab_;
	xsf77Call    xszvfe_;
	xsf77Call    xszvph_;
	xsf77Call    xszabs_;
	xsf77Call    xszwnb_;
	XSCCall      cflux;
	XSCCall      clumin;
	XSCCall      cpflux;
	XSCCall      gsmooth;
	XSCCall      ireflct;
	XSCCall      kdblur;
	XSCCall      kdblur2;
	XSCCall      spinconv;
	XSCCall      lsmooth;
	XSCCall      PartialCovering;
	XSCCall      rdblur;
	XSCCall      reflct;
	XSCCall      rfxconv;
	xsf77Call    rgsxsrc_;
	XSCCall      simpl;
	XSCCall      vashift;
	XSCCall      vmshift;
	XSCCall      xilconv;
	XSCCall      zashift;
	XSCCall      zmshift;
	XSCCall      pileup;
}


#endif
