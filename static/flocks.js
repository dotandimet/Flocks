// Called each time there's new content
window.tweak_content=function() {
    $('a:not(.internal-link, .anchor-link)').attr('target','_blank');
}

// The "OnLoad"
$(function() {
    $.manageAjax.create('flocks',{queue:true}); 
    $('.flashes li').each(function() {
        $(this).prepend($('<a/>').attr('href','#').click(function() {
            $(this).parent().remove(); return false;}).addClass(
                'internal-link important').append('<b/>').text('X')).css('opacity',.9)});
    $('body').append($('<a/>').attr('id','top-link').attr('href','#').addClass('internal-link').click(function() {
     	$('html,body').animate({scrollTop:0},'slow');
        return false;
    }).html('&#11014; Top'));
    $('#feed-url, #flockshare').click(function() {$(this).select()});
    $('.focusme:first').focus();
    window.tweak_content();
    if (window.SCROLLTO!=undefined && window.SCROLLTO) {
     	$('html,body').animate({scrollTop: $("#"+window.SCROLLTO).offset().top-60},'slow');
    }
});

window.populate_from_feed=function(ul,data) {
    for (e in data['entries']) { 
        if (e>=window.MAX_FEED_ENTRIES) { break; }
        entry=data['entries'][e];
        feed_dir=entry['feed_rtl']?'rtl':'ltr';
        var item_header=$('<div/>').addClass('toggler-label').addClass(feed_dir);
        item_header.append($('<div/>').addClass('item-time').text(entry['friendly_time']));
        item_header.append($('<span/>').addClass('feed-reference').text(entry['feed_title']).append(
            window.BUTTON_HTML[entry['feed_url']]));
        item_header.append($('<a/>').addClass('entry-title').attr(
            'href',entry['link']).html(entry['title']));
        var toggler = $('<input/>').addClass('toggler').attr('type','checkbox');
        if (window.EXPAND_ALL_ENTRIES) {toggler.attr('checked','checked');}
        var li=$('<li/>').attr('id',entry['id']).addClass('feed-entry').append(item_header).append(toggler);
        li.append($('<div/>').addClass('entry-description').addClass(feed_dir).html(entry['description']));
        li.data('modified',entry['modified']);
        var sameold=ul.find('#'+li.attr('id'));
        if (sameold.length) {
            // if it's hard to find out whether a checkbox is checked, might as well take the whole element :)
            li.find('input.toggler').replaceWith(sameold.find('input.toggler'));
            sameold.replaceWith(li);
        } else {
            var older=ul.find('li').filter(function() {
                return $(this).data('modified')<li.data('modified');
            });
            if (older.length) {
               	older.eq(0).before(li); 
            } else {
                ul.append(li);
            }
        };
        ul.children(':gt('+(window.MAX_PAGE_ENTRIES-1)+')').remove();
    }
}

window.fetch_from_feed=function(ul_id,feed_title,feed_url) {
    var ul=$('#'+ul_id);
    var loading=$('<li/>').addClass('fetching-ajax').html(AJAX_LOADER_HTML).append(feed_title).data('modified','');
    $('#loading-list').append(loading);
    $.manageAjax.add('flocks',{
        url:window.AJAX_FEED_URL,
        type:'POST',
        data:{url:feed_url},
        ul:ul,
        refresh:"window.fetch_from_feed('"+ul_id+"','"+feed_title+"','"+feed_url+"')",
        refresh_seconds:1000*window.FEED_REFRESH_SECONDS,
        loading:loading,
        success:function(data,textStatus,xhr,options){
            options['loading'].slideUp(500).remove();
            populate_from_feed(options['ul'],data);
            window.tweak_content();
            setTimeout(options['refresh'],options['refresh_seconds']);
        },
        error:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('Failed! ');
            options['loading'].prependTo($('#loading-list')).addClass(
                'hilite').click(function() {$(this).slideUp(1000).remove();});
            setTimeout(options['refresh'],options['refresh_seconds']);
        },
        abort:function(data,textStatus,xhr,options){
            options['loading'].find('img').replaceWith('Aborted! ');
            options['loading'].prependTo($('#loading-list')).addClass(
                'hilite').click(function() {$(this).slideUp(1000).remove();});
            setTimeout(options['refresh'],options['refresh_seconds']);
        }
    });
}
window.abort_all_fetches = function() {
    $.manageAjax.clear('flocks');
    $('.fetching-ajax').slideUp(500).remove();
}

